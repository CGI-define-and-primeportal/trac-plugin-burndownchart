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

            # List all valid option values - this reduces the chance
            # of values we don't expect being placed in the trac ini
            # The list of tuples is used later by the template data
            unit_options = [('hours', 'Hours'), ('points', 'Story Points'),
                            ('tickets', 'Tickets')]
            valid_units = [i[0] for i in unit_options]

            day_options = [('all', 'All'), ('weekdays', 'Weekdays')]
            valid_days = [i[0] for i in day_options]

            # we can't calculate this without work added information, so
            # we have to comment this out for now
            # ideal_options = [('fixed', 'Fixed'), ('variable', 'Variable')]
            # valid_ideal = [i[0] for i in ideal_options]

            if req.method == 'POST':

                unit_val = req.args.get('units')
                days_val = req.args.get('days')
                # ideal_val = req.args.get('ideal')


                # we only want to set a new value if its different to the current one
                # and a value we recognise from the appropriate options list
                #if ideal_val in valid_ideal and self.ideal_option != ideal_val:
                    #self.env.config.set('burndown', 'ideal', ideal_val)
                    #self.env.config.save()
                if unit_val in valid_units and self.unit_option != unit_val:
                        self.env.config.set('burndown', 'units', unit_val)
                        self.env.config.save()
                        add_notice(req, 'Burndown charts will now use %s for '
                        'their measure of effort' % (unit_val))
                if days_val in valid_days and self.day_option != days_val:
                        self.env.config.set('burndown', 'days', days_val)
                        self.env.config.save()
                        if days_val == 'all':
                            add_notice(req, 'Burndown charts will now include '
                            'all days (including weekends)')
                        elif days_val == 'weekdays':
                            add_notice(req, 'Burndown charts will now only '
                            'include weekdays (excluding Saturday and Sunday)')

            # Pass values to the template
            data = {'day_options': day_options,
                    'unit_options': unit_options,
                    #'ideal_options': ideal_options,
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
