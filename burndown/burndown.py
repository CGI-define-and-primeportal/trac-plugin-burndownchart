import pkg_resources
import re
from datetime import datetime, date, timedelta

from trac.admin.api import IAdminPanelProvider
from trac.core import *
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, add_stylesheet
from trac.web import IRequestHandler
from trac.ticket import Milestone #in model.py
from trac.web.api import IRequestFilter
from trac.ticket.query import Query
from trac.ticket import Ticket
from trachours.hours import TracHoursPlugin
from trac.ticket.api import ITicketChangeListener
from trac.util.datefmt import from_utimestamp, to_datetime

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

    implements(IRequestHandler, ITemplateProvider, IRequestFilter, ITicketChangeListener)

    # IRequestHandler methods

    def match_request(self, req):
        if re.match('/burndown', req.path_info):
            return True

    def process_request(self, req):
        if 'ROADMAP_VIEW' in req.perm:

            # Milestone is in model.py of trac/tickets
            db = self.env.get_db_cnx()
            milestones = Milestone.select(self.env, 'completed', db)

            milestone_info = dict()
            for milestone in milestones:
                if milestone.start and milestone.due:
                    milestone_info[milestone.name] = (milestone.name)

            data = {'milestones': milestone_info}

            # Get Milestone data
            date = (data.get('milestones')).get('milestone1')
            start_date = str(date).split(" ")[0]

            return 'burndown.html', data, None

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('burndown', pkg_resources.resource_filename(__name__,
                                                                'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        """Intercept POSTs to a specific milestone page"""

        # Matches /milestone/<anything except whitespace>
        if re.match('/milestone/[^ ]', req.path_info):
            pass
        return handler

    def post_process_request(self, req, template, data, content_type):

        if not re.match('/milestone/[^ ]', req.path_info):
            return template, data, content_type

        milestone = data['milestone']

        # If we don't have a start or due date for the milestone, don't
        # render the burndown chart
        if not milestone.start or not milestone.due:
            data['burndown'] = False # used by the milestone_view.html
            if not milestone.start:
                self.log.debug('Not generating burndown chart as %s is missing',
                                milestone.start)
            elif not milestone.due:
                self.log.debug('Not generating burndown chart as %s is missing',
                                milestone.due)
            return template, data, content_type

        # Get milestone information from data and convert datetime object
        # to string representation of a date object
        self.log.debug('Collecting data for burndown chart')
        data['burndown'] = True
        milestone_name = milestone.name
        milestone_start = str(milestone.start.date())
        milestone_due = str(milestone.due.date())

        # Burn down curve

        # Get ticket hours info using ticket ids and sum the total estimated
        # hours value for each ticket in the milestone
        hours = TracHoursPlugin(self.env)
        total_hours = 0
        # Query tickets in the milestone
        query = Query(self.env, constraints={'milestone': [milestone_name]})
        tickets = [i['id'] for i in query.execute(req)]
        for i in tickets:
            ticket = Ticket(self.env, tkt_id=i)
            total_hours += int(ticket['estimatedhours'])

        # Team effort curve

        # Calculate series of dates between a start and end date
        start = milestone.start.date()
        end = date.today() if date.today() <= milestone.due.date() \
              else milestone.due.date()
        dates = self.dates_inbetween(start, end)

        #self.env.config.set('burndown', 'workdays', 'all')
        self.env.config.set('burndown', 'workdays', 'weekdays')
        # self.env.config.set('burndown', 'workdays', 'custom')
        # self.env.config.set('')
        self.env.config.save()

        days_option = self.config.get('burndown', 'workdays')
        if days_option == 'weekdays':
            working_dates, non_working_dates = self.working_days(dates)
        elif days_option == 'custom':
            working_dates, non_working_dates = self.working_days(dates,
                                                             blacklisted_dates)

        # If user does not want to show non-working dates
        #if trac.config[]:
        #working_dates, non_working_dates = self.working_days(dates)
        #elif trac.config[]:
        #working_dates, non_working_dates = self.working_days(dates, blacklist)

        # Get hours logged on each day where work_logged is a dictionary of
        # key/value pairs representing date/seconds logged
        work_logged = {}
        for i in dates:
            date_logged, seconds = self.hours_logged(req, milestone_name, i)
            # date_logged needs to be a string for json
            str_date = date_logged.strftime('%Y-%m-%d')
            # effort needs to be in hours
            hours = seconds/float(60)/float(60)
            work_logged[str_date] = hours

        # Pass data to JS with JSON and make jqPlot library available
        self.log.debug('Passing data needed by burndown chart to JavaScript')

        add_script_data(req, {'burndowndata':
                                 {'name': milestone_name,
                                  'start_date':milestone_start,
                                  'end_date':milestone_due,
                                  'total_hours': total_hours,
                                  }
                              })

        add_script_data(req, {'teameffortdata': work_logged})

        add_script(req, 'burndown/js/burndown.js')

        # Adds jqPlot library needed by burn down charts
        add_script(req, 'common/js/jqPlot/jquery.jqplot.js')
        add_stylesheet(req, 'common/js/jqPlot/jquery.jqplot.min.css')
        add_script(req, 'common/js/jqPlot/plugins/jqplot.dateAxisRenderer.js')
        add_script(req, 'common/js/jqPlot/plugins/jqplot.highlighter.min.js')
        add_script(req,
                  'common/js/jqPlot/plugins/jqplot.canvasAxisLabelRenderer.js')

        return template, data, content_type

    # ITicketChangeListener

    def ticket_created(self, ticket):

        # if the ticket is added to a milestone that has already started
        # add the original estimate to the milestone

        # to update the remaining hours value

        # If a ticket is assigned to a milestone get the estimated hours value
        # Otherwise we look to see when this value is added at a later date
        # using the ticket_changed() method
        values = ticket.values
        if 'milestone' in values:
            original_estimate = values['estimatedhours']
            print original_estimate
            # if the milestone has started we need to increment 
            # the remaining hours value

    def ticket_changed(self, ticket, comment, author, old_values):
        """ You have to log hours against a particular ticket. This event is 
        recorded in the form of a comment to the ticket, which triggers the 
        ticket_changed() method. We then need to confirm that one of the
        modifications to the ticket included the logging of hours."""

        # Using the ticket id, worker name and time_submitted value to find
        # the hours logged in the ticket_time database table
        
        hours = TracHoursPlugin(self.env)
        values = ticket.values

        # Hacky condition to check if we are logging hours to a ticket
        # After adding a value the totalhours field must not be false (aka '')
        if values['totalhours'] and not old_values:
            change_time = values['changetime']
            ticket_log = hours.get_ticket_hours(ticket.id,
                                                from_date=date.today(),
                                                worker_filter=author)
            # Another check as ticket_log could be an empty dict
            if ticket_log:
                seconds_logged = ticket_log[-1]['seconds_worked']
                print seconds_logged

            # We could perform an additional check to compare the time when
            # the hours were logged to be sure it was correct
            # Note change_time is a datetime object but the time_submitted is
            # a timestamp
            # i['time_submitted']
            # to_datetime(i['time_submitted'])
            # change_time
            # from_utimestamp(i['time_submitted']) == change_time:
                #seconds_logged = i['seconds_worked']
                #print seconds_logged

    def ticket_deleted(self, ticket):

        # If a ticket is deleted, this might need to be reflected in the 
        # remaining work for each milestone
        pass

    def hours_logged(self, req, milestone, date):
        """Returns a integer to represent the total amount of hours
        logged against a group of tickets in a milestone on a certain
        date. Expects a milestone name and datetime object as arguments. 
        This is used to plot the team effort curve"""

        name = milestone

        # Get all tickets in the milestone
        hours = TracHoursPlugin(self.env)
        query = Query(self.env, constraints={'milestone': [name]})
        ticket_ids = [i['id'] for i in query.execute(req)]

        seconds_logged = 0
        for ticket_id in ticket_ids:
            time_logged = hours.get_ticket_hours(ticket_id, from_date=date,
                                                 to_date=date + timedelta(days=1))
            for i in time_logged:
                seconds_logged += i['seconds_worked']

        return date, seconds_logged

    def dates_inbetween(self, start, end):
        """Returns a list of datetime objects, with each item 
        representing a day in that period"""

        return [start + timedelta(days=i) for i in xrange((end - start).days + 1)]

    def working_days(self, dates, blacklisted_dates=None):
        """Expects a list of datetime objects, and if no blacklisted_dates 
        is passed removes any dates which fall on a Saturday or Sunday. 

        If blacklisted_dates is provided, all dates also in the dates 
        list are removed (note dates which fall on saturday or sunday have
        to be explicitly included in the blacklisted_dates list.

        Returns two lists, the first listing all working day and the second
        containing all non working days."""

        if not blacklisted_dates:
            work_dates = [date2 for date2 in dates if date2.weekday() < 5]
        else:
            work_dates = [date2 for date2 in dates if date2 not in set(blacklisted_dates)]
        non_working_dates = [date2 for date2 in dates if date2 not in set(work_dates)]

        return work_dates, non_working_dates

