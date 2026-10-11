# Run the Wisp prototype on your iPhone

This is a source-built prototype, not a TestFlight or App Store release. The
unsigned simulator build has been checked. Physical-device installation, signing
and UI behavior still need a user-run smoke test after the coordinator's review
checkpoint. No account access or model setup is needed for the fictional demo.

## Open a test copy on your Mac

Keep signing changes out of the reviewed source checkout. In Terminal, run:

```sh
WISP_IPHONE_TEST_DIR=$(mktemp -d "$HOME/Desktop/Wisp-iPhone-test.XXXXXX")
ditto /Users/adijain/Documents/Codex/2026-10-10/wisp-iphone-hackathon/ios "$WISP_IPHONE_TEST_DIR/ios"
open "$WISP_IPHONE_TEST_DIR/ios/WispPhone.xcodeproj"
```

This creates a new uniquely named Desktop folder. Use Xcode 27 or a compatible
newer Xcode with the required SDK. Your iPhone must run iOS 17 or later, and Xcode
must support its installed iOS version.

## Install from Xcode

1. Connect your iPhone to your Mac with a cable. Unlock it and tap **Trust** if
   asked to trust this Mac.
2. In Xcode, open **Settings → Apple Accounts** (called **Accounts** in some
   versions) and sign in to your Apple Account.
3. Select the blue **WispPhone** project, then the **WispPhone** target and
   **Signing & Capabilities**. Enable **Automatically manage signing** and choose
   your team or Personal Team. If Xcode asks for a unique bundle identifier, set
   one in this test copy, such as `com.adijain.wisp.iphonetest`.
4. Select **WispPhone** as the scheme and your connected iPhone as the run
   destination in Xcode's toolbar.
5. On the iPhone, enable **Settings → Privacy & Security → Developer Mode** if
   Xcode requests it. Restart, unlock and confirm **Turn On**. If the option is
   initially absent, connect the phone to Xcode first.
6. Press **⌘R** in Xcode. Xcode builds, signs, installs and opens Wisp. Follow any
   Xcode registration/signing prompts on your Mac.

These steps follow Apple's [device run instructions](https://help.apple.com/xcode/mac/current/en.lproj/dev5a825a1ca.html)
and [Developer Mode walkthrough](https://developer.apple.com/videos/play/wwdc2022/110344/).
A paid developer membership is not needed for this basic Personal Team test;
Personal Team provisioning expires and requires rebuilding periodically, as Apple
explains in its [account overview](https://developer.apple.com/help/account/basics/about-your-developer-account).
No Apple Account password or signing certificate needs to be sent to this chat.

## Five-minute test

Use **Reset to synthetic demo** first. The displayed source clock is fixed at
October 10, 2026, so “today” means that fixture day.

| Test | What to check |
| --- | --- |
| Ask `What is on my calendar today?` | Garden volunteering at 11 AM; no Wednesday midterm in today's view. |
| Ask `What did Mira say in messages?` | Both quoted messages with IDs; latest correction says west gate at 11. |
| Ask `Summarize Garden volunteers messages thread` | Earlier east-gate proposal before the later correction; historical caveat visible. |
| Ask `What groceries should I buy from notes?` | Pears (4) and oats; checked tea excluded. |
| Ask `When is my astronomy test?` | Astronomy midterm on October 14 at 1:30 PM. |
| Ask `Unread email` | Dario's poster-review request. |
| Action preview | Enter a fictional reminder and date, build and confirm. The app says no action performed. Editing any field removes the old preview/confirmation. |
| Import/reset | Paste harmless test text; scope says selected import. Reset returns to the fictional demo. |

Also check the keyboard, scrolling, text wrapping, VoiceOver labels and returning
from the background. Imported text is memory-only and may be discarded when the
app process ends. No Mail, Messages, Contacts, Calendar or Reminders permission
prompt is expected from these flows.

Report your iPhone model, iOS version, the exact question/test, expected versus
observed result, and any Xcode error text. Avoid including personal source content.
If signing fails, share the error text; do not delete certificates or change your
account configuration to troubleshoot blindly.
