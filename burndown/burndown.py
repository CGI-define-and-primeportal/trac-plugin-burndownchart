import pkg_resources
import re
from datetime import datetime, date, timedelta

from trac.admin.api import IAdminPanelProvider
from trac.core import Component, implements
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, add_stylesheet
from trac.web import IRequestHandler
from trac.ticket import Milestone #in model.py
from trac.web.api import IRequestFilter
from trac.ticket.query import Query
from trac.ticket import Ticket
from trachours.hours import TracHoursPlugin

# Author: Danny Milsom <danny.milsom@cgi.com>


class BurnDownCharts(Component):

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

        # Milestone has a start and due date so get information from data
        self.log.debug('Collecting data for burndown chart')
        data['burndown'] = True
        milestone_name = milestone.name
        milestone_start = milestone.start
        milestone_due = milestone.due

        # Convert from datetime objects to strings and remove the time value
        start_date_str = str(milestone_start).split(" ")[0]
        end_date_str = str(milestone_due).split(" ")[0]

        # Query tickets in the milestone
        query = Query(self.env, constraints={'milestone': [milestone_name]})
        query_results = [i['id'] for i in query.execute(req)]

        # Get ticket hours info using ticket ids
        hours = TracHoursPlugin(self.env)
        total_hours = 0
        seconds_logged = 0

        # Sum the total estimated hours values for each ticket in the milestone
        # and find all hours logged today
        for i in query_results:
            ticket = Ticket(self.env, tkt_id=i)
            total_hours += int(ticket['estimatedhours'])
            for i in hours.get_ticket_hours(i, from_date=date.today(),
                                          to_date=date.today() + timedelta(1)):
                seconds_logged += i['seconds_worked']

        print seconds_logged
        hours_logged = (seconds_logged/float(60))/float(60)
        print hours_logged

        # Pass data to JS with JSON and make jqPlot library available
        self.log.debug('Passing data needed by burndown chart to JavaScript')

        add_script_data(req, {'burndowndata':
                                 {'name': milestone_name, 
                                  'start_date':start_date_str,
                                  'end_date':end_date_str,
                                  'total_hours': total_hours,
                                  'hours_logged': hours_logged,}
                              })

        add_script(req, 'burndown/js/burndown.js')

        # Adds jqPlot library needed by burn down charts
        add_script(req, 'common/js/jqPlot/jquery.jqplot.js')
        add_stylesheet(req, 'common/js/jqPlot/jquery.jqplot.min.css')
        add_script(req, 'common/js/jqPlot/plugins/jqplot.dateAxisRenderer.js')
        add_script(req, 'common/js/jqPlot/plugins/jqplot.highlighter.min.js')
        add_script(req,
                  'common/js/jqPlot/plugins/jqplot.canvasAxisLabelRenderer.js')

        return template, data, content_type