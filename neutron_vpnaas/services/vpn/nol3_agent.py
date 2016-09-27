# Copyright 2013, Nachi Ueno, NTT I3, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from neutron.agent import l3_agent as entry
from neutron.agent import rpc as agent_rpc
from neutron.common import constants as l3_constants
from neutron.common import topics

from neutron import context as n_context
from neutron import manager

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import loopingcall

from neutron_lib import constants as lib_const

from neutron_vpnaas._i18n import _, _LE, _LI, _LW
from neutron_vpnaas.services.vpn import vpn_service

LOG = logging.getLogger(__name__)

vpn_agent_opts = [
    cfg.MultiStrOpt(
        'vpn_device_driver',
        default=['neutron_vpnaas.services.vpn.device_drivers.'
                 'ovn_ipsec.OvnSwanDriver'],
        sample_default=['neutron_vpnaas.services.vpn.device_drivers.'
                       'ovn_ipsec.OvnSwanDriver'],
        help=_("The vpn device drivers Neutron will use")),
]
cfg.CONF.register_opts(vpn_agent_opts, 'vpnagent')


class Nol3VPNAgent(manager.Manager):
    """VPNAgent class which can handle vpn service drivers."""
    def __init__(self, host, conf=None):
        if conf:
            self.conf = conf
        else:
            self.conf = cfg.CONF

        self.state_rpc = agent_rpc.PluginReportStateAPI(topics.REPORTS)
        self.context = n_context.get_admin_context_without_session()

        self.agent_state = {
            'binary': 'neutron-nol3vpn-agent',
            'host': host,
            'availability_zone': self.conf.AGENT.availability_zone,
            'topic': topics.L3_AGENT,
            'configurations': {
                'interface_driver': self.conf.interface_driver,
                'log_agent_heartbeats': self.conf.AGENT.log_agent_heartbeats},
            'start_flag': True,
            'agent_type': lib_const.AGENT_TYPE_L3}

        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            self.heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            self.heartbeat.start(interval=report_interval)

        self.service = vpn_service.VPNService(self)
        self.device_drivers = self.service.load_device_drivers(host)
        for driver in self.device_drivers:
            driver.sync(driver.context, [])

    def enqueue_state_change(self, router_id, state):
        pass

    def _report_state(self):
        try:
            agent_status = self.state_rpc.report_state(self.context,
                                                       self.agent_state,
                                                       True)
            if agent_status == l3_constants.AGENT_REVIVED:
                LOG.info(_LI('Agent has just been revived. '
                             'Doing a full sync.'))

            self.agent_state.pop('start_flag', None)

        except AttributeError:
            # This means the server does not support report_state
            LOG.warning(_LW("Neutron server does not support state report. "
                            "State report for this agent will be disabled."))
            self.heartbeat.stop()
            return
        except Exception:
            LOG.exception(_LE("Failed reporting state!"))

    def agent_updated(self, context, payload):
        """Handle the agent_updated notification event."""
        LOG.info(_LI("agent_updated by server side %s!"), payload)

    def after_start(self):
        #TBD, need to add process router loop for vpnaas
        #eventlet.spawn_n(self._process_routers_loop)

        LOG.info(_LI("VPN agent started"))
        # Do the report state before we do the first full sync.
        self._report_state()

    def routers_updated(self, context, routers):
        pass

    def router_deleted(self, context, router_id):
        pass


def main():
    entry.main(manager='neutron_vpnaas.services.vpn.nol3_agent.Nol3VPNAgent')
