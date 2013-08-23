import pkg_resources
import re
from datetime import datetime, date, timedelta, time

from trac.core import *
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, \
                            add_stylesheet, add_notice
from trac.web import ITemplateStreamFilter
from trac.ticket.api import ITicketActionController
from trac.web.api import IRequestFilter
from trac.util.datefmt import to_utimestamp, utc
from trac.config import Option
from itertools import groupby
from operator import itemgetter
from genshi.filters.transform import Transformer
from genshi.builder import tag
from trac.env import IEnvironmentSetupParticipant
from componentdependencies import IRequireComponents
from businessintelligenceplugin.history import HistoryStorageSystem
from logicaordertracker.controller import LogicaOrderController
from trac.util.compat import md5

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

    unit_value = Option('burndown', 'units', 'tickets',
                    doc="The units of effort for the burndown chart")

    day_value = Option('burndown', 'days', 'all',
                    doc="The different days to include in the burndown chart.")

    ideal_value = Option('burndown', 'ideal', 'fixed')

    implements(ITemplateProvider, IRequestFilter,
               ITicketActionController, ITemplateStreamFilter,
               IRequireComponents, IEnvironmentSetupParticipant)

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

        # Get milestone information from data
        self.log.debug('Collecting data for burndown chart')
        data['burndown'] = True
        milestone_name = milestone.name
        milestone_start = str(milestone.start.date())
        milestone_due = str(milestone.due.date())

        # Calculate series of dates between a start and end date
        start = milestone.start.date()
        end = date.today() if date.today() <= milestone.due.date() \
              else milestone.due.date()
        dates = self.dates_inbetween(start, end)
        all_milestone_dates = self.dates_inbetween(start, milestone.due.date())

        kwargs = {'daysback':0, 'ticket':'on', 'ticket_details': 'on',
                  'ticket_milestone_'+ md5(milestone_name).hexdigest(): 'on'}

        add_script_data(req, {'chartdata': 
                                {'name': milestone_name,
                                 'start_date': milestone_start,
                                 'end_date': milestone_due,
                                 'effort_units': self.unit_value,
                                 'timeline_url': req.href.timeline(kwargs),
                                 }
                            })

        self.log.debug('Connecting to the database to retrieve chart data')
        db = self.env.get_read_db()

        # Remaining Effort (aka burndown) Curve
        if self.unit_value == 'tickets':
            # Remaining Work Curve
            burndown_series = self.tickets_open_between_dates(db,
                                          milestone_name, milestone_start, end)
        elif self.unit_value == 'hours':
            # Remaining Work Curve
            burndown_series = self.hours_remaining_between_dates(db,
                                          milestone_name, milestone_start, end)
        elif self.unit_value == 'story_points':
            # Remaining Work Curve
            burndown_series = self.points_remaining_between_dates(db,
                                          milestone_name, milestone_start, end)

        # If we don't have any burndown data, exit and render normal milestone_view page
        if not burndown_series:
            data['burndown'] = False # Needed for stream filter
            return template, data, content_type

        add_script_data(req, {'burndowndata': burndown_series})

        # Work Added Curve
        work_added_data = self.work_added(burndown_series)
        add_script_data(req, {'workaddeddata': work_added_data})

        # Team Effort Curve
        work_logged = self.work_logged_curve(self.unit_value, milestone_name,
                                                milestone.start.date(), end, 
                                                self.dates_as_strings(dates))
        add_script_data(req, {'teameffortdata': work_logged})

        # Ideal Curve (unit value doesnt matter)
        if self.ideal_value == 'fixed':
            original_estimate = burndown_series[0][1]
        # If we want to include work added after the start date
        # in the ideal curve
        elif self.ideal_value == 'variable':
            original_estimate = burndown_series[0][1] + sum([added[1] for added in work_added_data])

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

    def work_logged_curve(self, metric, milestone_name, milestone_start, end, dates):
        """Returns a list of tuples, each representing the total number
        of tickets closed on each day for a respective milestone. If no
        tickets are closed, a tuple for that date will still be alongside
        included a 0 value.

        If the metric specified is tickets, the number of tickets closed
        on that date will be used. If the metric specified is hours, 
        the total amount of work logged in the ticket_time table
        against tickets in the milestone will be used. If the metric
        specified is story_points, the total amount of story points 
        for all tickets closed on that day will be used."""

        # Convert milestone start and end dates to timestamps
        start_stamp = to_utimestamp(datetime.combine(milestone_start,
                                            time(hour=0,minute=00,tzinfo=utc)))
        end_stamp = to_utimestamp(datetime.combine(end,
                                           time(hour=23,minute=59,tzinfo=utc)))

        db = self.env.get_read_db()
        cursor = db.cursor()

        # Get all statuses we consider to mean that the ticket is closed
        closed_statuses, types_and_statuses = self.closed_statuses_for_all_types()
        # Construct a query to identify all statuses in status groups we
        # considered closed
        closed_status_clause = ' OR '.join('(h.type = %%s AND c.newvalue IN (%s))'
                                      % ','.join('%s' for status in statuses)
                                      for type_, statuses in closed_statuses.iteritems())

        # This query looks in the history table to see which tickets
        # are in the defined milestone for each date (as this list can change
        # each day), and then looks to count how many of those tickets are
        # closed on each date by looking in the ticket_change table

        try:
            if metric == 'tickets':
                cursor.execute("""
                    SELECT COUNT(c.ticket),
                        (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date as day
                    FROM ticket_change AS c
                    JOIN ticket_bi_historical AS h
                        ON c.ticket = h.id
                        AND h._snapshottime = (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date
                    WHERE h.milestone = %%s
                        AND c.time >= %%s
                        AND c.time <= %%s
                        AND c.field = 'status'
                        AND (%s)
                    GROUP BY day;
                    """ % closed_status_clause,
                    [milestone_name, start_stamp, end_stamp] + types_and_statuses)
            elif metric == 'hours':
                cursor.execute("""
                    SELECT SUM(t.seconds_worked),
                        (timestamp with time zone 'epoch' + t.time_started * INTERVAL '1 second')::date as day
                    FROM ticket_time AS t
                    JOIN ticket_bi_historical AS h
                        ON t.ticket = h.id
                        AND h._snapshottime = (timestamp with time zone 'epoch' + t.time_started * INTERVAL '1 second')::date
                    WHERE h.milestone = %s
                    GROUP BY day;
                    """, [ milestone_name ])
            elif metric == 'story_points':
                cursor.execute("""
                    SELECT SUM(h.effort), h._snapshottime
                    FROM ticket_bi_historical AS h
                    JOIN ticket_change AS c ON h.id = c.ticket
                        AND h._snapshottime = (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date
                    WHERE h.milestone = %%s
                        AND c.time >= %%s
                        AND c.time <= %%s
                        AND c.field = 'status'
                        AND (%s)
                    GROUP BY h._snapshottime;
                    """ % closed_status_clause,
                    [milestone_name, start_stamp, end_stamp ] + types_and_statuses)
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        if metric == 'tickets':
            work_per_date = [(i[1].strftime('%Y-%m-%d'), int(i[0])) for i in cursor]
        elif metric == 'hours':
            work_per_date = [(i[1].strftime('%Y-%m-%d'), int(i[0])/float(60)/float(60)) for i in cursor]
        elif metric == 'story_points':
            work_per_date = [(i[1], int(i[0])) for i in cursor]

        # Add missing dates from milestone where no tickets were closed
        set_of_dates = set([i[0] for i in work_per_date])
        missing_dates = [(date, 0) for date in dates if date not in set_of_dates]

        return work_per_date + missing_dates

    def closed_statuses_for_all_types(self):
        """Returns a dictionary where the keys are tickets types and the associated
        values are statuses from workflow status groups where closed='True'. 

        Essentially if a ticket is in one of these statuses, we consider it closed
        and from this infer that no more work is required to complete the ticket.
        """

        controller = LogicaOrderController(self.env)
        closed_statuses = controller.type_and_statuses_for_closed_statusgroups()
        types_and_statuses = []
        for type_, statuses in closed_statuses.iteritems():
            types_and_statuses.append(type_)
            types_and_statuses.extend(statuses)

        return closed_statuses, types_and_statuses

    def tickets_in_milestone(self, milestone_name, milestone_start, end):
        """Returns a dictionary where the keys are dates between the 
        milestone start and end date arguments, and the associated value is 
        a set of all ticket ids within the milestone on that date."""

        db = self.env.get_read_db()
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, id
                FROM ticket_bi_historical
                WHERE milestone=%s
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s 
                ORDER BY _snapshottime ASC
                """, [ milestone_name, milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        data = {}
        for key, ticket in groupby(cursor, itemgetter(0)):
            data[key] = set([])
            for i in ticket:
                data[key].update([i[1]]) 
                # Note no sorting necessary as qpPlot does this for us

        return data

    def hours_remaining_between_dates(self, db, milestone_name,
                                      milestone_start, end):
        """Returns a list of tuples, each with a date and total remaining hours 
        value for all open tickets in that milestone.

        This data is used for the  burndown graph, if users want to show the 
        remaining effort burndown on a daily basis for all tickets. As a result 
        if work is added to the milestone after the start date, it is reflected 
        in this curve.

        Also note that if a ticket is closed, we consider there to be 0 remaining
        hours of effort remaining - even if the remaining effort value on the
        ticket suggests otherwise. This is necessary as if the ticket is closed,
        it is implied that there is no further work to complete."""

        self.log.debug('Querying the database for historical ticket hours data')
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime,
                SUM(estimatedhours), SUM(totalhours), SUM(remaininghours)
                FROM ticket_bi_historical
                WHERE milestone=%s
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s
                    AND isclosed = 'false'
                GROUP BY _snapshottime
                ORDER BY _snapshottime ASC
                """, [milestone_name, milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[3]) for i in cursor]

    def tickets_open_between_dates(self, db, milestone_name,
                                  milestone_start, end):
        """Returns a list of tuples, each with a date and value to represent 
        the total amount of tickets open for that milestone on a given date.

        This is primarily designed so we can draw the remaining effort curve
        on the burndown chart. The first tuple will always represent the first 
        day of the milestone, so that will also be used as the original effort
        value."""

        self.log.debug('Querying the database for historical tickets open data')
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, COUNT(DISTINCT id)
                FROM ticket_bi_historical
                WHERE milestone=%s
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s
                    AND isclosed = 'false'
                GROUP BY _snapshottime
                ORDER BY _snapshottime ASC
                """, [milestone_name, milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[1]) for i in cursor]

    def points_remaining_between_dates(self, db, milestone_name,
                                       milestone_start, end):
        """"""

        self.log.debug('Querying the database for historical effort/story point data')
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, SUM(effort)
                FROM ticket_bi_historical
                WHERE milestone=%%s
                    AND _snapshottime >=%%s
                    AND _snapshottime <=%%s
                    AND isclosed = 'false'
                GROUP BY _snapshottime
                """, [milestone_name, milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[1]) for i in cursor]

    def work_added(self, effort_data):
        """Iterates through all the days and remaining effort values shown on 
        the burndown chart, and calculates if the effort of work has increased.
        If it has the difference is calculated and placed in a tuple alongside
        the appropriate date. If remaining work is the same or less, the tuple
        includes a date and 0 value.""" 

        return [(data[0], 0) if i == 0
            else (data[0], data[1] - effort_data[i-1][1]) if data[1] > effort_data[i-1][1]
            else (data[0], 0)
            for i, data in enumerate(effort_data)]

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
        ideal_data = []

        for i, date in enumerate(self.dates_as_strings(dates)):
            if date in set(working_dates_str):
                ideal_data.append((date, original_estimate - 
                                (work_per_day*working_dates_str.index(date))))
            else:
                ideal_data.append((date, ideal_data[i-1][1]))

        return ideal_data

    def dates_as_strings(self, dates):
        """Returns string representation of all dates in a list"""

        return [i.strftime('%Y-%m-%d') for i in dates]

    def get_jqplot_file(self, filename):
        return "common/js/jqPlot/" + filename + ".js"

    # ITemplateStreamFilter
    def filter_stream(self, req, method, filename, stream, data):
        if filename == 'milestone_view.html':
            if data['burndown']:
                stream = stream | Transformer("//div[@class='row-fluid']").after(tag.div(id_='chart1', class_='box-primary'))
            else:
                html_text = 'To generate a burndown chart for this milestone please ensure there is a start and due date set. \
                This is configurable on the ', tag.a('milestone admin page. ', href=req.href.admin('ticket', 'milestones')), \
                'Please also check that the businessintelligenceplugin is enabled.'
                stream = stream | Transformer("//div[@class='row-fluid']").after(tag.div(html_text, id_='chart1', class_='box-info'))
        return stream

    # ITicketActionController methods

    def is_closed(req, ticket):
        pass

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('burndown', pkg_resources.resource_filename(__name__,
                                                                'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # IRequireComponents methods

    def requires(self):
        return [HistoryStorageSystem]

    # IEnvironmentSetupParticipant methods
    def environment_created(self):
        pass

    def environment_needs_upgrade(self, db):
        pass

    def upgrade_environment(self, db):
        pass
