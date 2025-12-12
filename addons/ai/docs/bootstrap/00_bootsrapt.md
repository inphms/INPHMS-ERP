### AI MODULE


# 1. @SystrayAction @ai/web/systray_action

1 single entry point.
- onClickLaunchAIChat():
    Called by:
        1. systray menu ai


# 2. @AiChatLauncherService @ ai/ai_chat_launcher_service

returning 2 method

1. launchAiChat():
    - Expect:
        - callerComponentName:
            1. mail_composer
            2. html_field_record
            3. html_field_text_select
            4. chatter_ai_button
            5. systray_ai_button
            

2. recordDataToContextJSON()

Called by:
    1. @SystrayAction
    2. FormControllerPatch
    3. ChatGPTPlugin
    4. MailComposerChatGPT