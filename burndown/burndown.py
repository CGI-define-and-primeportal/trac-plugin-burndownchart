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
from trac.util.datefmt import from_utimestamp, to_datetime
from trac.config import Option

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

    unit_value = Option('burndown', 'units', 'hours',
                    doc="The units of effort for the burndown chart")

    day_value = Option('burndown', 'days', 'all',
                    doc="The different days to include in the burndown chart.")

    implements(IRequestHandler, ITemplateProvider, IRequestFilter)

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

        # Calculate series of dates between a start and end date
        start = milestone.start.date()
        end = date.today() if date.today() <= milestone.due.date() \
              else milestone.due.date()
        dates = self.dates_inbetween(start, end)
        all_milestone_dates = self.dates_inbetween(start, milestone.due.date())

        add_script_data(req, {'burndowndata':
                                 {'name': milestone_name,
                                  'start_date':milestone_start,
                                  'end_date':milestone_due,
                                  'total_hours': total_hours,
                                  'effort_units': self.unit_value,
                                  }
                              })

        # Team effort curve
        if self.day_value == 'all':
            working_dates = dates
        elif self.day_value == 'weekdays':
            working_dates, non_working_dates = self.working_days(dates)
        elif self.day_value == 'custom':
            working_dates, non_working_dates = self.working_days(dates,
                                                             blacklisted_dates)

        # Get hours logged on each day where work_logged is a dictionary of
        # key/value pairs representing date/seconds logged
        work_logged = {}
        for i in working_dates:
            date_logged, seconds = self.hours_logged(req, milestone_name, i)
            # date_logged needs to be a string for json
            str_date = date_logged.strftime('%Y-%m-%d')
            # effort needs to be in hours
            hours = seconds/float(60)/float(60)
            work_logged[str_date] = hours
        add_script_data(req, {'teameffortdata': work_logged})

        # Ideal Curve
        work_dates, non_work_dates = self.get_date_values(all_milestone_dates)
        add_script_data(req, {'idealcurvedata':self.ideal_curve(total_hours,
                                                             all_milestone_dates,
                                                             work_dates),
                              })

        # Adds JS and jqPlot library needed by burn down charts
        add_script(req, 'burndown/js/burndown.js')
        add_script(req, self.get_jqplot_file('jquery.jqplot'))
        add_stylesheet(req, 'common/js/jqPlot/jquery.jqplot.min.css')
        add_script(req, self.get_jqplot_file('plugins/jqplot.dateAxisRenderer'))
        add_script(req, self.get_jqplot_file('plugins/jqplot.highlighter'))
        add_script(req, self.get_jqplot_file('plugins/jqplot.canvasTextRenderer'))
        add_script(req, self.get_jqplot_file('plugins/jqplot.canvasAxisTickRenderer'))
        add_script(req,
                  self.get_jqplot_file('plugins/jqplot.canvasAxisLabelRenderer'))

        return template, data, content_type

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return [('burndown', pkg_resources.resource_filename(__name__,
                                                                'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # Other methods for the class

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

    def get_date_values(self, all_dates):
        """Returns all working and non-working days in a milestone"""

        if self.day_value == 'all':
            working_dates = all_dates
            non_working_dates = []
        elif self.day_value == 'weekdays':
            working_dates, non_working_dates = self.working_days(all_dates)
        elif self.day_value == 'custom':
            working_dates, non_working_dates = self.working_days(all_dates,
                                                             blacklisted_dates)

        return working_dates, non_working_dates

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
            work_dates = [date2 for date2 in dates \
                          if date2 not in set(blacklisted_dates)]
        non_working_dates = [date2 for date2 in dates \
                            if date2 not in set(work_dates)]

        return work_dates, non_working_dates

    def ideal_curve(self, original_estimate, dates, working_dates):
        """Returns the average amount of work needed to remain on each day
        if the team is to finish all the work in a milestone/sprint by the
        due date, taking into account non working days.

        Also calls the dates_as_strings method first so the returned dict 
        can be passed straight to JSON."""

        work_per_day = float(original_estimate) / (len(working_dates) -1)
        working_dates_str = self.dates_as_strings(working_dates)
        working_dates_set = set(working_dates_str)
        dates_str = self.dates_as_strings(dates)
        ideal_curve_data = {}
        remaining_effort = original_estimate

        for i in reversed(dates_str):
            if i in working_dates_set:
                ideal_curve_data[i] = original_estimate - \
                                  (work_per_day*working_dates_str.index(i))
                remaining_effort = ideal_curve_data[i]
            else:
                ideal_curve_data[i] = remaining_effort

        return ideal_curve_data


    def dates_as_strings(self, dates):
        """Returns string representation of all dates in a list"""

        return [i.strftime('%Y-%m-%d') for i in dates]

    def get_jqplot_file(self, filename):
        return "common/js/jqPlot/" + filename + ".js"