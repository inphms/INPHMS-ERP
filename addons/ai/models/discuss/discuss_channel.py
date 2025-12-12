from __future__ import annotations
import logging

from datetime import timedelta

from inphms.orm import models, api, fields
from inphms.databases import SQL
from inphms.orm.fields import Command
from inphms.tools import _
from inphms.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):

    _inherit = ['discuss.channel']

    ai_agent_id = fields.Many2one("ai.agent", ondelete="set null", store=True, index=True, string="Ai Agent")
    ai_env_context = fields.Json("Context for AI agent", store=True)

    channel_type = fields.Selection(selection_add=[
        ('ai_chat', 'AI Chat')
    ], ondelete={'ai_chat': 'cascade',})


    def _get_ai_chat(self, agent_partner_ids):
        self.flush_model()
        self.env['discuss.channel.member'].flush_model()
        self.env.cr.execute(
            SQL(
                """
            SELECT M.channel_id
            FROM discuss_channel C, discuss_channel_member M
            WHERE M.channel_id = C.id
                AND M.partner_id IN %(partner_ids)s
                AND C.channel_type LIKE 'ai_chat'
                AND NOT EXISTS (
                    SELECT 1
                    FROM discuss_channel_member M2
                    WHERE M2.channel_id = C.id
                        AND M2.partner_id NOT IN %(partner_ids)s
                )
            GROUP BY M.channel_id
            HAVING ARRAY_AGG(DISTINCT M.partner_id ORDER BY M.partner_id) = %(sorted_partner_ids)s
            LIMIT 1
                """,
                partner_ids=tuple(agent_partner_ids),
                sorted_partner_ids=sorted(agent_partner_ids),
            )
        )
        result = self.env.cr.dictfetchall()
        return result

    @api.model
    def create_ai_draft_channel(self, caller_component_name, channel_title, record_model, record_id, front_end_record_info, text_selection):
        """ Creates a new AI chat channel (a draft thread) and
        returns its ID, initial data, and prompt buttons.

        :param caller_component_name: The name of the component that launched the AI chat (e.g., 'chatter_ai_button').
        :param channel_title: The suggested title for the new channel.
        :param record_model: The model name of the record the AI chat is related to.
        :param record_id: The ID of the record the AI chat is related to.
        :param front_end_record_info: Contextual data about the record from the frontend.
        :param text_selection: Any text selected by the user when launching the AI.
        :return: A dictionary containing the new channel ID, store data, and prompt buttons.
        """
        print("====" * 10)
        print(caller_component_name, channel_title, record_model, record_id, front_end_record_info, text_selection)
        READY_TO_GO = ["systray_ai_button"]
        if caller_component_name not in READY_TO_GO:
            _logger.warning(f"Houston, we have yet to setup for this {caller_component_name, channel_title, record_model, record_id, front_end_record_info, text_selection}")
        agents = self.env['ai.agent'].search([])
        print(agents, "agents")
        if agents.exists():
            agent_partner_id = agents.partner_id.id
            result = self._get_ai_chat([agent_partner_id])
            now = fields.Datetime.now()
            last_interest_dt = now - timedelta(seconds=1)
            if result:
                channel = self.browse(result[0].get('channel_id'))
            else:
                channel = self.with_user(self.env.user).create({
                    'name': channel_title or agents.partner_id.name,
                    'channel_partner_ids': [Command.link(self.env.user.partner_id.id), Command.link(agent_partner_id)],
                    'channel_type': 'ai_chat',
                    'ai_agent_id': agents.id
                })
            print(channel.ai_agent_id)
            print("====" * 10)
            store = Store(bus_channel=self.env.user)
            store.add(channel).add(channel, 'ai_agent_id')
            print(store.get_result())
            print("====" * 10)
            prompts = [
                "hello",
                "how are you"
            ]
            return {
                'ai_channel_id': channel.id,
                'data': store.get_result(),
                'prompts': prompts,
                'model_has_thread': "True",
            }
        
        print("====" * 10)
        # [{'id': 6, 'display_name': 'AI Chat with Chat AI', 'message_is_follower': False, 'message_follower_ids': [], 'message_partner_ids': [], 'message_ids': [], 'has_message': False, 'message_needaction': False, 'message_needaction_counter': 0, 'message_has_error': False, 'message_has_error_counter': 0, 'message_attachment_count': 0, 'name': 'AI Chat with Chat AI', 'active': True, 'channel_type': 'ai_chat', 'is_editable': True, 'default_display_mode': False, 'description': False, 'image_128': False, 'avatar_128': False, 'avatar_cache_key': 'no-avatar', 'channel_partner_ids': [6, 3], 'channel_member_ids': [9, 10], 'parent_channel_id': False, 'sub_channel_ids': [], 'from_message_id': False, 'pinned_message_ids': [], 'sfu_channel_uuid': False, 'sfu_server_url': False, 'rtc_session_ids': [], 'call_history_ids': [], 'is_member': True, 'self_member_id': (10, '“Administrator” in “AI Chat with Chat AI”'), 'invited_member_ids': [], 'member_count': 2, 'message_count': 0, 'last_interest_dt': datetime.datetime(2025, 11, 15, 3, 56, 21), 'group_ids': [], 'uuid': 'pnX49NtCKZ', 'group_public_id': False, 'invitation_url': '/chat/6/pnX49NtCKZ', 'channel_name_member_ids': [], 'create_uid': (2, 'Administrator'), 'create_date': datetime.datetime(2025, 11, 15, 3, 56, 22, 629382), 'write_uid': (2, 'Administrator'), 'write_date': datetime.datetime(2025, 11, 15, 3, 56, 22, 629382), 'ai_agent_id': False, 'ai_env_context': False}]
        # 20 
        # {discuss.channel: Array(1), 
        #  discuss.channel.member: Array(2), 
        #  res.partner: Array(2),
        #  res.users: Array(1)}
        # 
        #  discuss.channel: [{…}]
        #   0: ai_agent_id: 2
        #      channel_type: "ai_chat"
        #      create_uid: 2
        #      default_display_mode: false
        #      fetchChannelInfoState: "fetched"
        #      id: 20
        #      invited_member_ids: [Array(2)]
        #        0: (2) ['ADD', Array(0)]
        #           0: "ADD"
        #           1: []
        #           length: 2
        #           [[Prototype]]: Array(0)
        #        length: 1
        #        [[Prototype]]: Array(0)
        #      is_editable: true
        #      last_interest_dt: "2025-11-12 09:14:51"
        #      member_count: 2
        #      message_needaction_counter: 0
        #      message_needaction_counter_bus_id: 667
        #      name: "Ask AI"
        #      rtc_session_ids: [Array(2)]
        #        0: (2) ['ADD', Array(0)]
        #           length: 1
        #           [[Prototype]]: Array(0)
        #      uuid: "4NNxrnDHZf"
        #      [[Prototype]]: Object
        #      length: 1
        #      [[Prototype]]: Array(0)
        # 
        # discuss.channel.member: (2) [{…}, {…}]
        # res.partner: (2) [{…}, {…}]
        # res.users: [{…}][
        # [Prototype]]: Object (3) ['Which project costs us the most?', "What's my agenda for today?", 'Do I have any customer in Japan?']0: "Which project costs us the most?"1: "What's my agenda for today?"2: "Do I have any customer in Japan?"length: 3[[Prototype]]: Array(0) false