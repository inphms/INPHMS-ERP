from __future__ import annotations
import requests
import json
import logging

from inphms.orm import models, fields, api
from ..tools.cloudflare.worker_ai import prepare_cloudflare
from inphms.tools._vendor.safe_eval import safe_eval
from inphms.exceptions import UserError

_logger = logging.getLogger(__name__)


class AIAgent(models.Model):
    _name = "ai.agent"
    _description = ""
    _rec_name = "name"

    partner_id = fields.Many2one("res.partner", "Partner", ondelete="cascade", required=True, index=True)
    active = fields.Boolean("Active", store=True, default=True)

    @api.depends('topic_ids')
    def _compute_is_ask_ai_agent(self):
        """
        An agent is a "Natural Language Query Agent" if it includes the
        foundational 'ai_topic_information_retrieval_query' topic.
        """
        # Safer to use raise_if_not_found=False in case the XMLID is missing
        nlq_topic = self.env.ref('ai.ai_topic_information_retrieval_query', raise_if_not_found=False)
        
        if not nlq_topic:
            _logger.warning("The 'ai.ai_topic_information_retrieval_query' topic was not found. 'is_ask_ai_agent' will be False.")
            for agent in self:
                agent.is_ask_ai_agent = False
            return

        for agent in self:
            agent.is_ask_ai_agent = nlq_topic.id in agent.topic_ids.ids
    
    @api.depends('sources_ids', 'sources_ids.status')
    def _compute_sources_fully_processed(self):
        """
        Checks if all linked sources are in a 'indexed' state.
        
        NOTE: This requires your 'ai.agent.sources' model to have a
        'status' field (e.g., 'processing', 'indexed', 'failed').
        """
        for agent in self:
            if not agent.sources_ids:
                agent.sources_fully_processed = True  # No sources = fully processed
            else:
                agent.sources_fully_processed = all(
                    source.status == 'indexed' for source in agent.sources_ids
                )
    
    @api.model
    def _get_llm_model_selection(self):
        """
        Returns the list of available Cloudflare models.
        This can be expanded later to read from settings.
        """
        return [
            ('@cf/meta/llama-3-8b-instruct', 'Llama 3 8B Instruct'),
            ('@cf/mistral/mistral-7b-instruct-v0.1', 'Mistral 7B Instruct'),
            ('@cf/meta/llama-2-7b-chat-fp16', 'Llama 2 7B Chat (fp16)'),
            ('@cf/deepseek-ai/deepseek-coder-6.7b-instruct', 'DeepSeek Coder 6.7B'),
            # Add other models as needed
        ]

    image_128 = fields.Image("Image", related='partner_id.image_1920', store=False, readonly=False)
    avatar_128 = fields.Image("Avatar", related='partner_id.avatar_128', store=False)
    is_ask_ai_agent = fields.Boolean("Is Natural Language Query Agent", compute="_compute_is_ask_ai_agent", store=False)
    is_system_agent = fields.Boolean("System Agent", store=True)
    llm_model = fields.Selection(_get_llm_model_selection, 
                                 "LLM Model", store=True,
                                 required=True,
                                 default='@cf/meta/llama-3-8b-instruct')
    
    name = fields.Char(string="Agent Name", related="partner_id.name", required=True, readonly=False)
    response_style = fields.Selection([
        ('analytical', 'Analytical'),
        ('balanced', 'Balanced'),
        ('creative', 'Creative')
    ], string="Response Style", required=True, default="analytical")
    restrict_to_sources = fields.Boolean("Restrict to Sources", store=True, help="If checked, the agent will only respond based on the provided sources.")
    sources_fully_processed = fields.Boolean("Sources Fully Processed", compute="_compute_sources_fully_processed", store=False)
    sources_ids = fields.One2many("ai.agent.sources", "agent_id", "Sources")
    subtitle = fields.Char("Description", store=True)
    system_prompt = fields.Text("System Prompt", help="Customize to control relevance and formatting.", store=True)
    topic_ids = fields.Many2many("ai.topic", relation="ai_agent_ai_topic_rel", column1="ai_agent_id", column2="ai_topic_id",
                                 string="Topics", store=True, help="A topic includes instructions and tools that guide Inphms AI in helping the user complete their tasks.")
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner = self.env['res.partner'].sudo().create({
                    'name': vals.get('name') or 'Ask AI'
                })
                vals['partner_id'] = partner.id
        
        return super().create(vals_list)
    
    def _get_ai_response(self, conversation_history, current_view_info=None):
        """
        NEW: This method now calls the Cloudflare Workers AI API.
        'conversation_history' is expected to be a list of dicts:
        [
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'Hello!'},
            {'role': 'assistant', 'content': 'Hi! How can I help?_'},
            {'role': 'user', 'content': 'What is Inphms?'},
        ]
        """
        self.ensure_one()
        test_llm = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        api_url, headers = prepare_cloudflare(self.env, llm_model=test_llm)
        combined_instructions = self._get_combined_instructions()
        tools = self._get_tool_definitions()
        messages = [{'role': 'system', 'content': combined_instructions}]
        # Add Context Awareness
        if current_view_info and current_view_info.get('model'):
            context_msg = f"User Context: The user is currently viewing the Inphms model '{current_view_info.get('model')}'."
            if current_view_info.get('id'):
                context_msg += f" They are looking at the record with ID {current_view_info.get('id')}."
            messages.append({'role': 'system', 'content': context_msg})
        
        messages.extend(conversation_history)

        # 4. Start the API call loop (max 5 turns to prevent loops)
        for i in range(5):
            payload = {"messages": messages, "tools": tools}
            _logger.debug(f"Cloudflare Payload: {json.dumps(payload, indent=2)}")
            try:
                response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=60)
                response.raise_for_status()
                result = response.json()
                print("==" * 10)
                print("CLOUDFLARE RESULT", i)
                print(result)
                print("==" * 10)
                if not result.get('success'):
                    _logger.error(f"Cloudflare AI API Error: {result.get('errors')}")
                    return "I'm sorry, I received an error from the AI service."

                response_data = result.get('result', {})

                # === Case A: Final Text Response ===
                if response_data.get('response') is not None:
                    return response_data['response']

                # === Case B: Tool Call Response ===
                if response_data.get('tool_calls'):
                    _logger.info(f"AI requested tool calls: {response_data['tool_calls']}")
                    
                    # Add AI's "thought" (tool call) to history
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        # "tool_calls": response_data['tool_calls']
                    })

                    # Execute tools and gather results
                    tool_results = []
                    for tool_call in response_data['tool_calls']:
                        tool_output = self._execute_tool_call(tool_call)
                        tool_results.append({
                            "id": tool_call.get('id') or "000000001", # Match the call
                            "output": tool_output
                        })
                    
                    # Add tool results to history
                    messages.append({"role": "tool", "content": tool_results})
                    
                    # Continue loop to send results back to AI
                    continue 

                _logger.error(f"Cloudflare AI Error: Unexpected response format. {response_data}")
                return "I'm sorry, I received an unexpected response from the AI."

            except requests.exceptions.HTTPError as e:
                _logger.error(f"Cloudflare AI HTTP Error: {e.response.status_code} - {e.response.text}")
                return f"I'm sorry, I encountered an API error: {e.response.status_code}"
            except Exception as e:
                _logger.error(f"An unexpected error occurred during AI call: {e}", exc_info=True)
                return "I'm sorry, an unexpected error occurred."
        
        return "I'm sorry, I got stuck in a loop trying to find an answer. Please try rephrasing."

    # --- Tool Implementation Methods (Called by ir.actions.server) ---
    def _ai_tool_get_fields(self, model_name, include_description=True):
        """ Implements the 'get_fields' tool. """
        self.ensure_one()
        try:
            model = self.env[model_name]
            # You should add security here to check if this model is allowed
            # For now, we trust the topic setup.
            fields_data = model.fields_get(allfields=list(model._fields.keys()))
            
            # Format as CSV-like text as per your tool description
            output = ["field_name|display_name|type|sortable|groupable|description"]
            for name, data in fields_data.items():
                if not data.get('store', True):  # Skip non-stored fields
                    continue
                
                desc = data.get('help', '').replace('\n', ' ').replace('|', ' ') if include_description else ''
                line = [
                    name,
                    data.get('string', 'N/A').replace('|', ' '),
                    data.get('type', 'N/A'),
                    str(data.get('sortable', False)).lower(),
                    str(data.get('searchable', False)).lower(), # Assuming groupable ~ searchable
                    desc
                ]
                output.append("|".join(line))
            return "\n".join(output)
        except Exception as e:
            _logger.error(f"AI Tool 'get_fields' failed for model '{model_name}': {e}")
            return f"Error: Could not get fields for model '{model_name}'. Reason: {e}"

    def _ai_tool_read_group(self, model_name, domain, groupby, aggregates=None, having=None, offset=0, limit=None, order=None):
        """ Implements the 'read_group' tool. """
        self.ensure_one()
        try:
            # Domains from AI are JSON strings
            domain_list = json.loads(domain or '[]') if isinstance(domain, str) else domain
            
            # TODO: Add security check for model_name
            
            groups = self.env[model_name].sudo().read_group(
                domain=domain_list,
                fields=aggregates or [], # read_group uses 'fields' for aggregates
                groupby=groupby or [],
                offset=offset,
                limit=limit,
                orderby=order,
                lazy=False # Ensure all groups are computed
            )
            return json.dumps(groups, default=str) # Convert datetimes/decimals
        except Exception as e:
            _logger.error(f"AI Tool 'read_group' failed: {e}")
            return f"Error: {e}"

    def _ai_tool_search(self, model_name, domain, fields=None, offset=0, limit=None, order=None):
        """ Implements the 'search' (search_read) tool. """
        self.ensure_one()
        try:
            # Domains from AI are JSON strings
            domain_list = json.loads(domain or '[]') if isinstance(domain, str) else domain
            
            # TODO: Add security check for model_name
            print(domain_list)
            records = self.env[model_name].sudo().search_read(
                domain=domain_list,
                fields=fields or [],
                offset=offset,
                limit=limit,
                order=order,
            )
            return json.dumps(records, default=str) # Convert datetimes/decimals
        except Exception as e:
            _logger.error(f"AI Tool 'search' failed: {e}")
            return f"Error: {e}"
        
    # --- Tool Definition & Execution Helpers (NEW) ---
    
    def _get_combined_instructions(self):
        """ Combines agent system_prompt + all topic instructions. """
        self.ensure_one()
        
        # Start with the agent's base prompt
        instructions = [self.system_prompt or "You are a helpful assistant."]
        
        # Add instructions from each topic
        for topic in self.topic_ids:
            if topic.instructions:
                instructions.append(f"\n--- Instructions for Topic: {topic.name} ---\n{topic.instructions}")
        
        return "\n".join(instructions)

    def _get_tool_definitions(self):
        """ Gathers all tools from all topics and formats them for Cloudflare. """
        self.ensure_one()
        tools = []
        tool_actions = self.topic_ids.mapped('tool_ids').filtered('use_in_ai')
        
        for action in tool_actions:
            if not action.ai_tool_has_schema:
                _logger.warning(f"AI Tool '{action.name}' is missing a valid schema and will be skipped.")
                continue
            try:
                tools.append({
                    "name": action.name,
                    "description": action.ai_tool_description,
                    "parameters": json.loads(action.ai_tool_schema)
                })
            except Exception as e:
                _logger.error(f"Failed to parse schema for AI Tool '{action.name}': {e}")
        
        return tools

    def _execute_tool_call(self, tool_call):
        """ Finds and runs the ir.actions.server code for a given tool call. """
        self.ensure_one()
        tool_name = tool_call.get('name')
        tool_args = tool_call.get('arguments', {})
        
        # Find the server action
        action = self.env['ir.actions.server'].search([
            ('name', '=', tool_name),
            ('use_in_ai', '=', True)
        ], limit=1)
        
        if not action:
            _logger.error(f"AI tried to call unknown or disabled tool: {tool_name}")
            return json.dumps({"error": f"Tool '{tool_name}' not found or is not an AI tool."})

        # Prepare the environment for safe_eval
        # The 'code' in your XML (e.g., ai['result'] = record._ai_tool_search(...))
        # will be executed in this context.
        eval_context = {
            'env': self.env,
            'model': self.env[action.model_id.sudo().model],
            'record': self,  # 'record' in the code field refers to this ai.agent
            'records': self,
            'ai': {},  # This dict will store the 'result'
            'log': _logger.info,
            'UserError': UserError,
        }
        # set default
        # 1. Initialize eval_context with defaults (order, offset, limit, etc.)
        # You can set defaults manually or read them if your schema supports it.
        default_args = {
            # Default for 'order' if not provided by the AI
            'order': '', 
            # Default for 'offset' (can be 0 or None, depending on ORM function)
            'offset': 0, 
            # Default for 'limit'
            'limit': None, 
            # Default for domain and fields, which are sometimes required but need to be safe
            'domain': [],
            'fields': [],
            # Add other optional params with safe defaults
        }
        eval_context.update(default_args)

        # Add all tool arguments (e.g., model_name, domain) to the context
        eval_context.update(tool_args)

        parsed_tool_args = {}

        for key, value in tool_args.items():
            if key in ('domain', 'fields', 'groupby', 'aggregates', 'having') and isinstance(value, str):
                try:
                    # Attempt to parse the string as JSON
                    parsed_value = json.loads(value)
                    parsed_tool_args[key] = parsed_value
                except json.JSONDecodeError:
                    # If parsing fails, use the original string value
                    parsed_tool_args[key] = value
            else:
                # For non-JSON or non-string arguments, use the original value
                parsed_tool_args[key] = value
        eval_context.update(parsed_tool_args)

        try:
            _logger.info(f"AI executing tool '{tool_name}' with args: {tool_args}, eval_context: {eval_context}, parsed args: {parsed_tool_args}")
            # Run the server action's code
            safe_eval(action.code.strip(), eval_context, mode="exec")
            
            # Get the result from the 'ai' dict
            result = eval_context.get('ai', {}).get('result')
            
            # Return the result as a JSON string
            if isinstance(result, (dict, list)):
                return json.dumps(result, default=str)
            return str(result)

        except Exception as e:
            _logger.error(f"Execution of AI tool '{tool_name}' failed: {e}", exc_info=True)
            return json.dumps({"error": f"Tool execution failed: {e}"})
