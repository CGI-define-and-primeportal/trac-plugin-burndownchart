import pkg_resources
import re
from datetime import datetime, date, timedelta, time

from trac.core import *
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, \
                            add_stylesheet, add_notice, add_ctxtnav
from trac.web import ITemplateStreamFilter
from trac.ticket.model import Milestone
from trac.web.api import IRequestFilter, IRequestHandler
from trac.util.datefmt import to_utimestamp, utc,to_timestamp
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
from trac.util.presentation import to_json
from trac.resource import ResourceNotFound

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

    unit_value = Option('burndown', 'units', 'tickets',
                    doc="The units of effort for the burndown chart")

    day_value = Option('burndown', 'days', 'all',
                    doc="The different days to include in the burndown chart.")

    ideal_value = Option('burndown', 'ideal', 'fixed')

    implements(ITemplateProvider, IRequestFilter,
               ITemplateStreamFilter, IRequireComponents,
               IEnvironmentSetupParticipant, IRequestHandler)

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        """The actual burndown chart is generated and rendered after page load 
        using a AJAX call which is picked up by the match_request() and 
        process_request() methods.

        This method determines if we should send that AJAX call, by 
        checking the milestone has both a start and end date. If so, the 
        jqPlot JS files are loaded and the script data 'render_burndown'  
        passed via JSON."""

        # check we are on an individual milestone page
        if req.path_info.startswith("/milestone/") \
            and "burndown" not in req.path_info and "stats" in data:

            milestone = self._get_milestone(req)
            if milestone:
                # Load the burn down JS file
                add_script(req, 'burndown/js/burndown.js')

                # If we don't have a start or due date for the milestone, don't
                # try and render the burndown chart
                if not milestone.start or not milestone.due:
                    add_script_data(req, {'render_burndown': False,
                                         })
                    return template, data, content_type
                # If we do, tell JS it should send a request via JSON
                # and use the defualt effort value
                else:
                    add_script_data(req, {'render_burndown': True,
                                          'milestone_name': milestone.name,
                                          'print_burndown': False,
                                          'effort_units': self.unit_value,
                                          })

                # Add a burndown unit option to the context nav
                add_ctxtnav(req, tag.div(
                                    tag.a(
                                        tag.i(class_="icon-bar-chart "),
                                    " Units"),
                                    tag.ul(
                                        tag.li(
                                            tag.a('Tickets', href=None, id_="tickets-metric"),
                                        ),
                                        tag.li(
                                            tag.a('Hours', href=None, id_="hours-metric"),
                                        ),
                                        tag.li(
                                            tag.a('Story Points', href=None, id_="points-metric"),
                                        ),
                                        class_="styled-dropdown fixed-max"
                                    ),
                                    class_="dropdown-toggle inline block",
                                  )
                            )

                # Add a print link to the context nav
                add_ctxtnav(req, tag.a(
                                    tag.i(class_="icon-print"),
                                " Print", id_="print-burndown"))

                # Adds jqPlot library needed by burndown charts
                self._add_static_files(req)

        return template, data, content_type

    # IRequestHandler

    def match_request(self, req):
        """Requests to this URL are usually sent via AJAX or when 
        printing the burn down chart. In both cases we expect a URL 
        to start with /milestone/milestone_name/burndown. Its important
        that we check to see if the the milestone exists, as another 
        IRequestHandler opens a new milestone template when a user
        references a non existant milestone. Additional arguments are 
        delt with by the process_request."""

        if req.path_info.startswith("/milestone/"):
            # Check that the milestone exists
            milestone = self._get_milestone(req)
            if milestone:
                return milestone.name + "/burndown" in req.path_info

    def process_request(self, req):
        """Collect the data needed for a burndown chart and pass to JavaScript. 
        If the original request was via AJAX we use to_json, otherwise
        we return data via add_script_data."""

        # Get milestone object and all child milestones
        milestone = self._get_milestone(req)
        tree = Milestone.build_tree(self.env)
        all_milestones = [m.name for m in tree.find(milestone.name).traverse()]

        # If anyone request milestone/milestonename/burndown not via AJAX
        # and not with a format argument (eg when printing) , we redirect to 
        # milestone/milestonename, as we need to load pre_process_request first
        XMLHttp = req.get_header('X-Requested-With') == 'XMLHttpRequest'
        if not XMLHttp and 'format' not in req.args:
            req.redirect(req.href.milestone(milestone.name))

        # Calculate series of dates between a start and end date
        start = milestone.start.date()
        if date.today() <= milestone.due.date():
            end = date.today()
            dates = self.dates_inbetween(start, end - timedelta(days=1))
        else:
            end = milestone.due.date()
            dates = self.dates_inbetween(start, end)
        all_milestone_dates = self.dates_inbetween(start, milestone.due.date())

        # Open a database connection
        self.log.debug('Connecting to the database to retrieve chart data')
        db = self.env.get_read_db()

        # If no metric data is posted, use the project default self.unit_value
        metric = req.args.get('metric', self.unit_value)

        # Remaining Effort (aka burndown) Curve
        remaining_effort_args = [db, all_milestones, str(start), end]

        burndown_series = []
        if metric == 'tickets':
            burndown_series = self.tickets_open_between_dates(*remaining_effort_args)
        elif metric == 'hours':
            burndown_series = self.hours_remaining_between_dates(*remaining_effort_args)
        elif metric == 'points':
            burndown_series = self.points_remaining_between_dates(*remaining_effort_args)

        # If we don't have any burndown data send a message and stop
        if not burndown_series:
            data = {'result': False}
            # For ajax request
            if XMLHttp:
                req.send(to_json(data), 'text/json')
            else:
                return 'burndown_print.html', data, None

        # Team Effort Curve
        team_effort = self.team_effort_curve(db, metric, all_milestones,
                                                start, end,
                                                self.dates_as_strings(dates))

        # Work Added Curve
        # We don't calculate this right now as the algorithm only works
        # when using a ticket metric - see #3850
        #work_added_data = self.work_added(burndown_series, team_effort)

        # Ideal Curve (unit value doesnt matter)
        if self.ideal_value == 'fixed':
            original_estimate = burndown_series[0][1]
        # If we want to include work added after the start date
        # in the ideal curve
        elif self.ideal_value == 'variable':
            original_estimate = burndown_series[0][1] + sum([added[1] for added in work_added_data])

        work_dates, non_work_dates = self.get_date_values(all_milestone_dates)
        ideal_data = self.ideal_curve(original_estimate, all_milestone_dates,
                                                             work_dates)

        data = {
            'burndowndata': burndown_series,
             #'workaddeddata': work_added_data,
            'teameffortdata' : team_effort,
            'idealcurvedata': ideal_data,
            'milestone_name': milestone.name,
            'start_date': str(start),
            'end_date': str(milestone.due.date()),
            'effort_units': metric,
            'yaxix_label': metric.title(),
            'result' : True,
        }

        # Ajax request
        if XMLHttp:
            kwargs = {  'daysback':0,
                        'ticket':'on',
                        'ticket_details': 'on',
                        'ticket_milestone_'+ md5(milestone.name).hexdigest(): 'on'
                     }
            data.update({
              'timeline_url': req.href.timeline(kwargs),
              'print_burndown': False,
              'render_burndown': True,
            })

            req.send(to_json(data), 'text/json')

        # Normal request (eg the print friendly page)
        else:
            if req.args.get('format') == 'print':
                # Load the burn down JS file and jqPlot library 
                add_script(req, 'burndown/js/burndown.js')
                self._add_static_files(req)

                result = {'data': data,
                          'print_burndown': True,
                          'render_burndown': True,
                          'result': True,
                         }

                add_script_data(req, result)
                return 'burndown_print.html', result, None

    # Other methods for the class
    def _get_milestone(self, req):
        """Returns a milestone instance if one exists, or None if it
        does not."""
        milestone_name = req.path_info.split("/")[2]
        milestone = None
        if milestone_name:
            try:
                milestone = Milestone(self.env, milestone_name)
            except ResourceNotFound:
                milestone = None
        return milestone

    def _get_jqplot(self, filename):
        """Quick reference to the location of jqPlot files"""
        return "common/js/jqPlot/" + filename + ".js"

    def _add_static_files(self, req):
        """Adds all the jqPlot JS files we need for the burndown charts"""
        add_script(req, self._get_jqplot('jquery.jqplot'))
        add_stylesheet(req, 'common/js/jqPlot/jquery.jqplot.css')
        # excanvas is needed for IE8 support
        add_script(req, self._get_jqplot('excanvas.min'))
        add_script(req, self._get_jqplot('plugins/jqplot.dateAxisRenderer'))
        add_script(req, self._get_jqplot('plugins/jqplot.highlighter'))
        add_script(req, self._get_jqplot('plugins/jqplot.canvasTextRenderer'))
        add_script(req, self._get_jqplot('plugins/jqplot.canvasAxisTickRenderer'))
        add_script(req, self._get_jqplot('plugins/jqplot.canvasAxisLabelRenderer'))
        add_script(req, self._get_jqplot('plugins/jqplot.enhancedLegendRenderer'))

    def team_effort_curve(self, db, metric, milestone_names, milestone_start, end, dates):
        """Returns a list of tuples, each representing the total number
        of tickets closed on each day for a respective milestone. If no
        tickets are closed, a tuple for that date will still be alongside
        included a 0 value.

        If the metric specified is tickets, the number of tickets closed
        on that date will be used. If a ticket is reopened after it is
        closed, we will not count that ticket as effort.

        If the metric specified is hours, the total amount of work logged 
        in the ticket_time table against tickets in the milestone on 
        a given day will be used.

        If the metric specified is story_points, the total amount of story points 
        for all tickets closed on that day will be used."""

        # Convert milestone start and end dates to timestamps based on metric
        if metric == 'hours':
            start_stamp = to_timestamp(datetime.combine(milestone_start,
                                        time(hour=0,minute=00,tzinfo=utc)))
            end_stamp = to_utimestamp(datetime.combine(end,
                                       time(hour=23,minute=59,tzinfo=utc)))
        else: # must be tickets or story points
            start_stamp = to_utimestamp(datetime.combine(milestone_start,
                                            time(hour=0,minute=00,tzinfo=utc)))
            end_stamp = to_utimestamp(datetime.combine(end,
                                           time(hour=23,minute=59,tzinfo=utc)))

        # Create a custor to access the database
        cursor = db.cursor()

        # Get all statuses we consider to mean that the ticket is closed
        closed_statuses, types_and_statuses = self.closed_statuses_for_all_types()

        # These queries all rely on a join with the ticket_bi_historical
        # table to see which tickets were in the defined milestone 
        # on a given day
        try:
            if metric == 'tickets':
                cursor.execute("""
                    SELECT c.ticket,
                        (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date as day,
                        h.type,
                        c.oldvalue,
                        c.newvalue
                    FROM ticket_change AS c
                    JOIN ticket_bi_historical AS h
                        ON c.ticket = h.id
                        AND h._snapshottime = (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date
                    WHERE h.milestone IN ({0})
                        AND c.time >= %s
                        AND c.time <= %s
                        AND c.field = 'status'
                    ORDER BY c.time ASC
                    """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [start_stamp, end_stamp])
            elif metric == 'hours':
                cursor.execute("""
                    SELECT SUM(t.seconds_worked),
                        (timestamp with time zone 'epoch' + t.time_started * INTERVAL '1 second')::date as day
                    FROM ticket_time AS t
                    JOIN ticket_bi_historical AS h
                        ON t.ticket = h.id
                        AND h._snapshottime = (timestamp with time zone 'epoch' + t.time_started * INTERVAL '1 second')::date
                    WHERE h.milestone IN ({0})
                        AND t.time_started >= %s
                        AND t.time_started <= %s
                    GROUP BY day;
                    """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [start_stamp, end_stamp])
            elif metric == 'points':
                cursor.execute("""
                    SELECT h.id,
                           h._snapshottime,
                           h.type,
                           c.oldvalue,
                           c.newvalue,
                           h.effort
                    FROM ticket_bi_historical AS h
                    JOIN ticket_change AS c ON h.id = c.ticket
                        AND h._snapshottime = (timestamp with time zone 'epoch' + c.time/1000000 * INTERVAL '1 second')::date
                    WHERE h.milestone IN ({0})
                        AND c.time >= %s
                        AND c.time <= %s
                        AND c.field = 'status'
                    ORDER BY h._snapshottime
                    """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [start_stamp, end_stamp])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        if metric == 'hours':
            work_per_date = [(i[1].strftime('%Y-%m-%d'),
                              float(i[0])/60/60) for i in cursor]
        else:
            # must be tickets or story points
            work_per_date = self.count_tickets_closed(cursor, closed_statuses, metric)

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

    def tickets_in_milestone(self, milestone_names, milestone_start, end):
        """Returns a dictionary where the keys are dates between the 
        milestone start and end date arguments, and the associated value is 
        a set of all ticket ids within the milestone on that date."""

        db = self.env.get_read_db()
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, id
                FROM ticket_bi_historical
                WHERE milestone IN ({0})
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s 
                ORDER BY _snapshottime ASC
                """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [milestone_start, end])
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

    def hours_remaining_between_dates(self, db, milestone_names,
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
                    SUM(remaininghours)
                FROM ticket_bi_historical
                WHERE milestone IN ({0})
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s
                    AND isclosed = 0
                GROUP BY _snapshottime
                ORDER BY _snapshottime ASC
                """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[1]) for i in cursor]

    def tickets_open_between_dates(self, db, milestone_names,
                                  milestone_start, end):
        """Returns a list of tuples, each with a date and value to represent 
        the total amount of tickets open for that milestone on a given date.

        This is primarily designed so we can draw the remaining effort curve
        on the burndown chart. The first tuple will always represent the first 
        day of the milestone."""

        self.log.debug('Querying the database for historical tickets open data')
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, COUNT(DISTINCT id)
                FROM ticket_bi_historical
                WHERE milestone IN ({0})
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s
                    AND isclosed = 0
                GROUP BY _snapshottime
                ORDER BY _snapshottime ASC
                """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[1]) for i in cursor]

    def points_remaining_between_dates(self, db, milestone_names,
                                       milestone_start, end):
        """"""

        self.log.debug('Querying the database for historical effort/story point data')
        cursor = db.cursor()
        try:
            cursor.execute("""
                SELECT _snapshottime, SUM(effort)
                FROM ticket_bi_historical
                WHERE milestone IN ({0})
                    AND _snapshottime >=%s
                    AND _snapshottime <=%s
                    AND isclosed = 0
                GROUP BY _snapshottime
                """.format(','.join(('%s',)*len(milestone_names))), milestone_names + [milestone_start, end])
        except Exception:
            db.rollback()
            self.log.exception('Unable to query the historical ticket table')
            return []

        return [(str(i[0]), i[1]) for i in cursor]

    def work_added(self, effort_data, logged_data):
        """To calculate the amount of work added each day we find the 
        difference between the remaining effort data points on days n 
        and n-1. We then add the work logged on day n to calculate the 
        amount of work added (or removed)."""

        # Work can be added by:
        # * creating a new ticket in the milestone
        # * moving a ticket into the milestone
        # * increases the remaining estimated effort / story points
        # Luckily we don't need to worry about that with this algorithm

        remaining_difference = [(data[0], 0) if i == 0
                                else (data[0], data[1] - effort_data[i-1][1])
                                for i, data
                                in enumerate(sorted(effort_data, key=itemgetter(0)))]

        # We assume that the remaining_difference and logged data are 
        # the same length, so each tuple we iterate over in each list
        # relates to the same date (hence the sort)

        # Note that if the remaining diff is negative, we use zero value
        # see https://d4.define.logica.com/ticket/3727

        return [(remaining[0], max(0, remaining[1] + logged[1]))
                for remaining, logged
                in zip(remaining_difference,sorted(logged_data, key=itemgetter(0)))]

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

        try:
            work_per_day = float(original_estimate) / (len(working_dates) -1)
        except ZeroDivisionError:
            # the milestone is only 1 day long
            work_per_day = original_estimate
        ideal_data = []
        work_days = 0
        # we set ideal_for_date and last_day_amount to original estimate
        # to handle cases when the first day in the milestone is a weekend
        ideal_for_date = last_day_amount = original_estimate

        for date in self.dates_as_strings(dates):
            if date in set(working_dates_str):
                ideal_for_date = original_estimate - (work_per_day*work_days)
                ideal_data.append((date, ideal_for_date))
                work_days += 1
            else:
                ideal_data.append((date, last_day_amount))

            last_day_amount = ideal_for_date

        return ideal_data

    def count_tickets_closed(self, cursor, closed_statuses, metric):
        """This is used to render the work logged curve, and counts 
        the number of tickets moved from an open to closed 
        status on a given day. If a ticket is re-opened
        after it has already been closed on a day, we will
        no longer count that ticket as closed for the purposes
        of this count.

        # change[0] is ticket id
        # change[1] is date changed
        # change[2] is ticket type
        # change[3] is old status value
        # change[4] is new status value
        # change[5] is effort value (only for story point metric)"""

        # Group changes by date
        closed_per_date = []
        for date, changes in groupby(cursor, itemgetter(1)):
            closed_ids = []
            effort = {}
            for change in changes:
                # Get all closed statuses for ticket type
                closed_status_for_type = closed_statuses[change[2]]

                # if moved from an open to closed status
                if change[3] not in closed_status_for_type and change[4] in closed_status_for_type:
                    closed_ids.append(change[0])

                    # keep track of story point values for each ticket
                    if len(change) >= 6 and change[0] not in effort:
                        # use id for key, points for the value
                        effort[change[0]] = change[5]

                # if moved from a closed status to open
                if change[3] in closed_status_for_type and change[4] not in closed_status_for_type:
                    # remove id from our list and story points from effort
                    try:
                        closed_ids.remove(change[0])
                        del effort[change[0]]
                    except (ValueError, KeyError):
                        # we don't catch worry about these exceptions as
                        # sometimes the ticket wont be in closed_ids or effort
                        pass

            if metric =='tickets':
                # List of tuples (date, closed_count)
                closed_per_date.append((date.strftime('%Y-%m-%d'), len(closed_ids)))
            elif metric == 'story_points':
                # List of tuples (date, total of effort for all closed tickets)
                closed_per_date.append((date.strftime('%Y-%m-%d'), sum(effort.values())))

        return closed_per_date

    def closed_status_clause(self, closed_statuses):
        """Returns a SQL clause which lists all ticket types
        and the closed statuses associated with their workflow."""

        return ' OR '.join('(h.type = %%s AND c.newvalue IN (%s))'
                            % ','.join('%s' for status in statuses)
                            for type_, statuses in closed_statuses.iteritems())

    def dates_as_strings(self, dates):
        """Returns string representation of all dates in a list"""

        return [i.strftime('%Y-%m-%d') for i in dates]

    # ITemplateStreamFilter
    def filter_stream(self, req, method, filename, stream, data):
        if re.match('/milestone/[^ ]', req.path_info):
            help_page_url = req.href.help('DefineGuide', 'DefineAgile', 'BurndownCharts')
            stream = stream | Transformer("//*[@id='milestone-overview']").after(tag(
                                                                                    tag.h2("Burn Down Chart ", 
                                                                                        tag.a(
                                                                                            tag.i(class_="icon-question-sign color-muted", id_="burndown_more_info"), 
                                                                                        href=help_page_url, target="_blank")
                                                                                        ), 
                                                                                    tag.div(id_='milestone-burndown', class_='milestone-info')
                                                                                    )
                                                                                )

        return stream

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
