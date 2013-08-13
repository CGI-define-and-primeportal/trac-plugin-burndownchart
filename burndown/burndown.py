import pkg_resources
import re
from datetime import datetime, date, timedelta, time

from trac.core import *
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, \
                            add_stylesheet, add_notice
from trac.web import IRequestHandler
from trac.ticket import Milestone #in model.py
from trac.ticket.api import ITicketActionController
from trac.web.api import IRequestFilter
from trac.ticket.query import Query
from trac.ticket import Ticket
from trachours.hours import TracHoursPlugin
from trac.util.datefmt import from_utimestamp, to_datetime, to_utimestamp, to_timestamp, utc
from trac.config import Option
from itertools import groupby
from operator import itemgetter

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

    unit_value = Option('burndown', 'units', 'hours',
                    doc="The units of effort for the burndown chart")

    day_value = Option('burndown', 'days', 'all',
                    doc="The different days to include in the burndown chart.")

    implements(IRequestHandler, ITemplateProvider, IRequestFilter,
               ITicketActionController)

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
            if not milestone.start and not milestone.due:
                add_notice(req, 'Unable to generate a burndown chart as this \
                                 milestone has no start or due date')
            elif not milestone.start:
                add_notice(req, 'Unable to generate a burndown chart as the \
                                 milestone start date has not been specified')
            elif not milestone.due:
                add_notice(req, 'Unable to generate a burndown chart as the \
                                 milestone due date has not been specified')
            return template, data, content_type

        # Get milestone information from data and convert datetime object
        # to string representation of a date object
        self.log.debug('Collecting data for burndown chart')
        data['burndown'] = True
        milestone_name = milestone.name
        milestone_start = str(milestone.start.date())
        milestone_due = str(milestone.due.date())

        # Burn down curve

        # Calculate series of dates between a start and end date
        start = milestone.start.date()
        end = date.today() if date.today() <= milestone.due.date() \
              else milestone.due.date()
        dates = self.dates_inbetween(start, end)
        all_milestone_dates = self.dates_inbetween(start, milestone.due.date())

        add_script_data(req, {'chartdata': 
                                {'name':milestone_name,
                                 'start_date':milestone_start,
                                 'end_date':milestone_due,
                                 'effort_units':self.unit_value,
                                 'timeline_url':req.href.timeline(daysback=0,
                                              ticket='on', ticket_details='on')
                                 }
                            })

        # Conntect to database and retrieve the ticket_bi_historical table data
        # for the appropriate milestone upto today or the milestone date.

        #################################################################
        # TODO
        # Only query for tickets which are not closed
        # There us the is_closed() method in ITicketActionController but ideally
        # we would get a list of all valid closed workflow states
        ################################################################
        db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.unit_value == 'tickets':
            # Remaining Work Curve
            burndown_series = self.tickets_open_between_dates(cursor, 
                                          milestone_name, milestone_start, end)
            original_estimate = burndown_series[0][1]
            # Team Effort Curve
            work_logged = self.tickets_closed(milestone_name,
                                                milestone.start.date(), end, 
                                                self.dates_as_strings(dates))
            #print work_logged
            #import pdb; pdb.set_trace()

        elif self.unit_value == 'hours':
            # Remaining Work Curve
            burndown_series = self.hours_remaining_between_dates(cursor, 
                                          milestone_name, milestone_start, end)
            original_estimate = burndown_series[0][1]
            # Team Effort Curve
            work_logged = self.team_effort_in_hours_curve(req, milestone_name, 
                                                                         dates)

        elif self.unit_value == 'story points':
            pass # do something

        # Pass curve data to JS via JSON
        add_script_data(req, {'burndowndata': burndown_series})
        add_script_data(req, {'teameffortdata': work_logged})

        # Ideal Curve (unit value doesnt matter)
        work_dates, non_work_dates = self.get_date_values(all_milestone_dates)
        add_script_data(req, {'idealcurvedata':self.ideal_curve(original_estimate,
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
        add_script(req, self.get_jqplot_file('plugins/jqplot.enhancedLegendRenderer'))

        return template, data, content_type

    # Other methods for the class

    def team_effort_in_hours_curve(self, req, milestone_name, dates):
        """Get hours logged on each day where work_logged is a list of 
        tuples with key/value pairs representing date/seconds logged. 
        
        We check all days even if the user has marked weekends as non 
        working days. This is important to give a true reflection of the 
        teams efforts."""

        work_logged = []
        for date in dates:
            date_logged, seconds = self.hours_logged(req, milestone_name, date)
            # date_logged needs to be a string for json
            str_date = date_logged.strftime('%Y-%m-%d')
            # effort needs to be in hours
            hours = seconds/float(60)/float(60)
            work_logged.append((str_date, hours))

        return work_logged

    def hours_logged(self, req, milestone_name, date):
        """Returns a integer to represent the total amount of hours
        logged against a group of tickets in a milestone on a certain
        date. Expects a milestone name and datetime object as arguments. 
        This is used to plot the team effort curve"""

        # Get all tickets in the milestone
        hours = TracHoursPlugin(self.env)
        query = Query(self.env, constraints={'milestone': [milestone_name]})
        ticket_ids = [i['id'] for i in query.execute(req)]

        seconds_logged = 0
        for ticket_id in ticket_ids:
            time_logged = hours.get_ticket_hours(ticket_id, from_date=date,
                                            to_date=date + timedelta(days=1))
            for i in time_logged:
                seconds_logged += i['seconds_worked']

        return date, seconds_logged

    def tickets_closed(self, milestone_name, milestone_start, end, dates):
        """Returns a list of tuples, each representing the total number
        of tickets closed on each day for a respective milestone. If no
        tickets are closed, a tuple for that date will still be included
        alongside a 0 value."""

        # Convert milestone start and end dates to timestamps
        start_stamp = to_utimestamp(datetime.combine(milestone_start,
                                            time(hour=0,minute=00,tzinfo=utc)))
        end_stamp = to_utimestamp(datetime.combine(end,
                                           time(hour=23,minute=59,tzinfo=utc)))

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        # This query looks in the history table to see which tickets 
        # are in the defined milestone for each date (as this list can change 
        # each day), and then looks to count how many of those tickets are
        # closed on each date by looking in the ticket_change table
        try:
            cursor.execute("""
                select count(c.ticket),
                       (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date as day
                from ticket_change as c
                join ticket_bi_historical as h on c.ticket = h.id and h.snapshottime = (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date
                where c.field = 'status'
                and c.newvalue = 'closed'
                and h.milestone = %s
                and c.time >= %s
                and c.time <= %s
                group by day;
                """, [ milestone_name, start_stamp, end_stamp ])
        except Exception, e:
            db.rollback()
            self.log.error('Unable to query the historical ticket table')
            self.log.error(e)

        closure_dates = [(i[1].strftime('%Y-%m-%d'), int(i[0])) for i in cursor]

        # Add missing dates from milestone where no tickets were closed
        set_of_closure_dates = set([i[0] for i in closure_dates])
        for date in dates:
            if date not in set_of_closure_dates:
                closure_dates.append((date, 0))

        return closure_dates

    def tickets_in_milestone(self, milestone_name, milestone_start, end):
        """Returns a dictionary where the keys are dates between the 
        milestone start and end date arguments, and the associated value is 
        a set of all ticket ids within the milestone on that date."""

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT snapshottime, id
                FROM ticket_bi_historical WHERE milestone=%s AND snapshottime >=%s
                AND snapshottime <=%s ORDER BY snapshottime ASC
                """, [ milestone_name, milestone_start, end])
        except Exception, e:
            db.rollback()
            self.log.error('Unable to query the historical ticket table')
            self.log.error(e)

        data = {}
        for key, ticket in groupby(cursor, itemgetter(0)):
            data[key] = set([])
            for i in ticket:
                data[key].update([i[1]]) 
                # Note no sorting necessary as qpPlot does this for us

        return data

    def hours_remaining_between_dates(self, cursor, milestone_name, milestone_start, end):

        self.log.debug('Querying the database for historical ticket hours data')
        try:
            cursor.execute("""
                SELECT snapshottime,
                SUM(estimatedhours), SUM(totalhours), SUM(remaininghours)
                FROM ticket_bi_historical WHERE milestone=%s AND snapshottime >=%s
                AND snapshottime <=%s AND status != 'closed' GROUP BY snapshottime
                ORDER BY snapshottime ASC
                """, [ milestone_name, milestone_start, end])
        except Exception, e:
            db.rollback()
            self.log.error('Unable to query the historical ticket table')
            self.log.error(e)

        return [(str(i[0]), i[3]) for i in cursor]

    def tickets_open_between_dates(self, cursor, milestone_name, milestone_start, end_date):
        """Returns a list of tuples, each with a date and value to represent 
        the total amount of tickets open for that milestone on a given date.

        This is primarily designed so we can draw the remaining effort curve
        on the burndown chart. The first tuple will always represent the first 
        day of the milestone, so that will also be used as the original effort
        value."""

        self.log.debug('Querying the database for historical tickets open data')
        try:
            cursor.execute("""
                SELECT snapshottime, COUNT(DISTINCT id) FROM ticket_bi_historical
                WHERE milestone=%s AND snapshottime>=%s AND snapshottime <=%s 
                AND status!='closed' 
                GROUP BY snapshottime ORDER BY snapshottime ASC
                """,[ milestone_name, milestone_start, end_date])
        except Exception, e:
            db.rollback()
            self.log.error('Unable to query the historical ticket table')
            self.log.error(e)

        return [(str(i[0]), i[1]) for i in cursor]

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
        are passed removes any dates which fall on a Saturday or Sunday. 

        If blacklisted_dates is provided, all dates also in the dates 
        list are removed (note dates which fall on saturday or sunday have
        to be explicitly included in the blacklisted_dates list).

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

        Also calls the dates_as_strings method first so the returned list 
        can be passed straight to JSON."""

        work_per_day = float(original_estimate) / (len(working_dates) -1)
        working_dates_str = self.dates_as_strings(working_dates)
        ideal_curve_data = []

        for i, date in enumerate(self.dates_as_strings(dates)):
            if date in set(working_dates_str):
                ideal_curve_data.append((date, original_estimate - \
                                  (work_per_day*working_dates_str.index(date))))
            else:
                ideal_curve_data.append((date, ideal_curve_data[i-1][1]))

        return ideal_curve_data

    def dates_as_strings(self, dates):
        """Returns string representation of all dates in a list"""

        return [i.strftime('%Y-%m-%d') for i in dates]

    def get_jqplot_file(self, filename):
        return "common/js/jqPlot/" + filename + ".js"

    # ITicketActionController methods

    def is_closed(req, ticket):
        pass

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('burndown', pkg_resources.resource_filename(__name__,
                                                                'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]