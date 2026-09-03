"""
selectors.py — every WhatsApp Web selector lives HERE and nowhere else.

WhatsApp Web changes its DOM without warning. When posting suddenly stops
working, this is the only file you need to touch. Run:

    python wacd.py --probe

to open WhatsApp Web and dump what the page actually looks like right now
(saved to probe/), then fix the lists below.

Each entry is a LIST of candidates, tried in order. Adding a new candidate at
the TOP is always safe: old ones stay as fallbacks.
"""

WHATSAPP_URL = "https://web.whatsapp.com/"

# Proof that we are logged in (any one of these means the app has loaded).
LOGGED_IN = [
    '#pane-side',
    '[data-testid="chat-list"]',
    '[aria-label="Chat list"]',
]

# The QR / login screen — if any of these is visible we are NOT logged in.
NEEDS_LOGIN = [
    'canvas[aria-label*="Scan"]',
    '[data-testid="qrcode"]',
    'div[data-ref]',
]

# One-off interstitials WhatsApp Web shows in a fresh profile ("What's new on
# WhatsApp Web", cookie/consent notices, feature announcements). They sit on top
# of everything and silently block automation, so they are dismissed first.
# Text-matched on purpose: a broad 'dialog button' rule would also hit the media
# preview's own controls.
INTERSTITIAL_DISMISS = [
    'div[role="dialog"] button:has-text("Continue")',
    'div[role="dialog"] button:has-text("Got it")',
    'div[role="dialog"] button:has-text("OK")',
    'div[role="dialog"] button:has-text("Not now")',
    'button:has-text("Continue")',
    'button:has-text("Got it")',
]

# The close (X) on such a dialog, when it has no button we recognise.
INTERSTITIAL_CLOSE = [
    'div[role="dialog"] [aria-label="Close"]',
    'div[role="dialog"] span[data-icon="x"]',
    'div[role="dialog"] button[aria-label*="lose"]',
]

# The "Channels" tab in the left navigation rail.
CHANNELS_TAB = [
    '[aria-label="Channels"]',
    '[data-testid="channels-tab"]',
    'button[aria-label*="Channel"]',
    'span[data-icon="newsletter-outline"]',
    'span[data-icon="channels-outline"]',
]

# The search box used to find a channel by name.
SEARCH_BOX = [
    '[data-testid="chat-list-search"]',
    'div[contenteditable="true"][data-tab="3"]',
    'div[contenteditable="true"][aria-label*="Search"]',
    'p.selectable-text[contenteditable="true"]',
]

# A row in the channel/chat list. {name} is substituted with the channel name.
CHANNEL_ROW = [
    '#pane-side span[title="{name}"]',
    'span[title="{name}"]',
    'div[role="listitem"]:has-text("{name}")',
]

# The hidden <input type=file> WhatsApp uses for image/video attachments.
# Setting files on this directly is far more stable than clicking the 📎 menu.
FILE_INPUT_MEDIA = [
    'input[type="file"][accept*="image"]',
    'input[type="file"][accept*="video"]',
    'input[type="file"]',
]

# The caption box shown in the media preview dialog, before sending.
CAPTION_BOX = [
    '[data-testid="media-caption-input-container"] div[contenteditable="true"]',
    'div[contenteditable="true"][aria-label*="caption"]',
    'div[contenteditable="true"][aria-label*="Caption"]',
    'div[contenteditable="true"][data-tab="10"]',
    'div[contenteditable="true"][data-tab="1"]',
]

# The plain message composer (used for text-only posts).
COMPOSER = [
    'footer div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"]',
    'div[contenteditable="true"][aria-label*="Type a message"]',
]

# The send button in the media preview dialog.
SEND_BUTTON = [
    '[data-testid="send"]',
    'span[data-icon="send"]',
    'button[aria-label="Send"]',
    'div[role="button"][aria-label="Send"]',
]

# Anything here being present means the media composer is open and ready.
# Kept deliberately broad: the composer is recognised by ANY of its parts —
# the send button, the caption box, or the image-editing toolbar along the top.
MEDIA_DIALOG = [
    'span[data-icon="send"]',
    '[data-testid="media-preview"]',
    '[data-testid="media-caption-input-container"]',
    'div[data-animate-modal-body="true"]',
    'span[data-icon="crop-image"]',
    'span[data-icon="media-editor-drawing"]',
    'button[aria-label="Send"]',
    'div[role="button"][aria-label="Send"]',
]
