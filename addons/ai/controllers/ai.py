from __future__ import annotations

from inphms.server import Controller, route
from inphms.server.utils import request
from inphms.exceptions import UserError
from inphms.tools import html2plaintext


class Ai(Controller):

    @route("/ai/generate_response", methods=['POST'], type="jsonrpc", auth="user")
    def generate_response(self, mail_message_id, channel_id, current_view_info=None, ai_session_identifier=None):
        """ Triggers the AI to generate a response
        to the user's message in the specified channel.
        """
        print("AI GENERATE RESPONSE")
        print(mail_message_id, channel_id, current_view_info, ai_session_identifier)

        user = request.env.user
        channel = request.env['discuss.channel'].browse(channel_id).exists()
        message = request.env['mail.message'].browse(mail_message_id).exists()

        if not channel or channel.channel_type != 'ai_chat' or not channel.ai_agent_id:
            return {'error': 'Invalid AI chat channel or agent not found.'}

        if not message or message.author_id != user.partner_id:
            return {'error': 'Invalid user message.'}

        # 1. Get the conversation history
        # Fetch all messages in the channel to provide context to the AI
        messages = channel.message_ids.sorted(key='id')
        conversation_history = []
        for msg in messages:
            # Skip system notifications or error messages
            if msg.message_type != 'comment' or not msg.body:
                continue
                
            # Remove HTML tags from the message body for the AI
            prompt_text = html2plaintext(msg.body)
            
            if msg.author_id == channel.ai_agent_id.partner_id:
                role = 'assistant'
            else:
                role = 'user'
            
            conversation_history.append({'role': role, 'content': prompt_text})
        
        # 2. Prepare the prompt for the AI
        # This is where you would format the conversation history and the new message
        # into a format suitable for your AI model (e.g., OpenAI chat format).
        
        # For simplicity, we'll just use the last message's body as the prompt
        user_prompt = message.body
        
        # 3. Call the AI service (Placeholder for actual AI call)
        # In a real scenario, this would involve an external API call.
        try:
            # Simulate AI response generation
            ai_response_text = channel.ai_agent_id._get_ai_response(conversation_history)
            
            # 4. Post the AI's response back to the channel
            channel.with_context(mail_create_nosubscribe=True).message_post(
                body=ai_response_text,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=channel.ai_agent_id.partner_id.id,
            )
            
            return {'success': True}
            
        except Exception as e:
            raise e
        

    @route("/ai/post_error_message", methods=['POST'], type="jsonrpc", auth="user")
    def post_error_message(self, error_message, channel_id):
        """ Posts a system message to the chat channel
        when an error occurs during AI response generation.
        """
        channel = request.env['discuss.channel'].browse(channel_id).exists()
        if not channel:
            return {'error': 'Invalid channel.'}

        # Post the error message as a system notification
        # channel.message_post(
        #     body=f"**AI Error:** {error_message}",
        #     message_type='notification',
        #     subtype_xmlid='mail.mt_note',
        #     author_id=request.env.ref('base.partner_root').id, # Use a system partner
        # )
        # return {'success': True}
        print(error_message, channel_id)
        raise UserError(error_message)
    
    @route("/ai/close_ai_chat", type="jsonrpc", methods=['POST'], auth="user")
    def close_ai_chat(self, channel_id):
        """ Cleans up resources or marks the AI chat session
        as closed when the chat window is dismissed.
        """
        channel = request.env['discuss.channel'].browse(channel_id).exists()
        if channel and channel.channel_type == 'ai_chat':
            # Example cleanup: delete the channel if it's a draft and has no user messages
            if len(channel.message_ids) <= 1: # Only the initial context message
                channel.unlink()
                return {'deleted': True}
            
            # Or, you might archive it, or simply do nothing if you want to keep the history
            return {'success': True}
            
        return {'error': 'Invalid AI chat channel.'}
    