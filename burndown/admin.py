import pkg_resources
from trac.core import *
from trac.web.chrome import ITemplateProvider, add_script, add_notice
from trac.admin.api import IAdminPanelProvider
from trac.config import Option
from trac.ticket import Milestone

# Author: Danny Milsom <danny.milsom@cgi.com>

class BurndownAdmin(Component):

    implements(ITemplateProvider, IAdminPanelProvider)

    unit_option = Option('burndown', 'units', 'tickets',
                    doc="The units of effort for the burndown chart")

    day_option = Option('burndown', 'days', 'all',
                    doc="The different days to include in the burndown chart.")

    ideal_option = Option('burndown', 'ideal', 'fixed',
                    doc="""The values to include in the ideal curve. If fixed
                    the ideal curve will only ever include the effort assigned
                    to the milestone on its start date. If variable work added
                    after the milestone has started will be included.""")

    # IAdminPanelProvider

    def get_admin_panels(self, req):
        if 'LOGIN_ADMIN' in req.perm:
            yield ('reporting', ('Reporting'),
           'burndown_charts', ('Burndown Charts'))

    def render_admin_panel(self, req, category, page, path_info):
        if page == 'burndown_charts':
            if req.method == 'POST':
                if req.args['ideal']:
                    self.env.config.set('burndown', 'ideal', req.args['ideal'])
                    self.env.config.save()
                if req.args['units'] and req.args['days']:
                    if self.unit_option != req.args['units']:
                        self.env.config.set('burndown', 'units', req.args['units'])
                        self.env.config.save()
                        add_notice(req, 'Burndown charts will now use %s for '
                        'their measure of effort' % (req.args['units']))
                    if self.day_option != req.args['days']:
                        self.env.config.set('burndown', 'days', req.args['days'])
                        self.env.config.save()
                        if req.args['days'] == 'all':
                            add_notice(req, 'Burndown charts will now include '
                            'all days (including weekends)')
                        elif req.args['days'] == 'weekdays':
                            add_notice(req, 'Burndown charts will now only '
                            'include weekdays (excluding Saturday and Sunday)')

            # Pass values to the template
            data = {'day_options': [('all', 'All'),
                                    ('weekdays', 'Weekdays')],
                    'unit_options': [('hours', 'Hours'),
                                    ('story_points', 'Story Points'),
                                    ('tickets', 'Tickets')],
                    'ideal_options': [('fixed', 'Fixed'),
                                      ('variable', 'Variable')],
                    'current_day_value' : self.day_option,
                    'current_unit_value' : self.unit_option,
                    'current_ideal_value' : self.ideal_option,
                    'applicable_milestones' : self.milestones_with_start_and_end(),
                    }

            add_script(req, 'burndown/js/burndown_admin.js')

            return 'burndown_admin.html', data

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('burndown', pkg_resources.resource_filename(__name__,
                                                                'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    def milestones_with_start_and_end(self):
        db = self.env.get_db_cnx()

        return [milestone.name \
                for milestone in Milestone.select(self.env, 'completed', db) \
                if milestone.start and milestone.due]
