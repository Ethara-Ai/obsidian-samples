# Tools: Brittany Morales

## Tool Usage

### Connected Services

#### Brittany's accounts
- **Gmail** (`gmail-api`): Her inbox at brittany.morales@greenridertech.co: clients, sellers such as Joanne Ellery, vendors, Tom Henderson and family.
- **Google Calendar** (`google-calendar-api`): Her calendar in Eastern Time (showings, open houses, closings, family), plus the Ellery family calendar, which Joanne Ellery shares with her for showings and open houses at 5759 W Sea Grape Ln.
- **Google Drive** (`google-drive-api`): Her listing folders, shared with each seller and with Gabriela Santos, who drops her photo sets there; the 5759 W Sea Grape Ln folder holds Joanne's floor-plan scan, filled questionnaire and coming-soon graphic and Gabi's first two photos and shoot notes. Her own Instagram folder holds the images her posts pull from.
- **Notion** (`notion-api`): Her listing tracker: the Listings database (one record per listing, the fields she enters on Stellar MLS, each record a page for her notes) and her Listing launch standards page. Tom Henderson reviews every new listing before it goes live and leaves his broker-review notes on its page.
- **Instagram** (`instagram-api`): @brittany.morales.homes, her business account: feed posts, stories, comments and insights, toward the 10K-follower goal.

#### Connected, not Brittany's accounts
These connectors are linked to this assistant, but each one signs in to a shared demo workspace or to someone else's account. Nothing in them is Brittany's, so treat what they hold as other people's data, never as hers.
- **BigCommerce** (`bigcommerce-api`): online store catalogue, orders and customers.
- **Box** (`box-api`): cloud file storage and shared folders.
- **Calendly** (`calendly-api`): booking pages and scheduled meetings.
- **Contentful** (`contentful-api`): content management: content types, entries and assets.
- **DocuSign** (`docusign-api`): e-signature envelopes and templates.
- **Duffel** (`duffel-api`): flight search, offers and holds.
- **Facebook** (`facebook-api`): pages, posts and groups.
- **FlightAware** (`flightaware-api`): live flight tracking and airport data.
- **Function Health** (`function-health-api`): lab panels and biomarker results.
- **Google Contacts** (`google-contacts-api`): an address book.
- **Google Docs** (`google-docs-api`): documents.
- **Google Forms** (`google-forms-api`): forms and their responses.
- **Google Sheets** (`google-sheets-api`): spreadsheets.
- **Google Slides** (`google-slides-api`): presentations.
- **Google Tasks** (`google-tasks-api`): to-do lists.
- **Granola** (`granola-api`): meeting notes and transcripts.
- **Health** (`health-api`): sleep, heart-rate and activity data.
- **HealthEx** (`healthex-api`): patient medical records.
- **Home Assistant** (`home-assistant-api`): smart-home devices and automations.
- **Instagram Messages** (`instagram-messages-api`): direct messages.
- **Jira** (`jira-api`): issue tracking boards.
- **Messenger** (`messenger-api`): chat threads.
- **Monday** (`monday-api`): work boards and items.
- **OpenTable** (`opentable-api`): restaurant search and reservations.
- **Outlook** (`outlook-api`): Microsoft 365 mail.
- **Outlook Calendar** (`outlook-calendar-api`): Microsoft 365 calendars.
- **Outlook Contacts** (`outlook-contacts-api`): Microsoft 365 contacts.
- **Peloton** (`peloton-api`): workout classes and history.
- **Philips Hue** (`philips-hue-api`): smart lights and scenes.
- **Phone** (`phone-api`): calls and text messages.
- **Plaid** (`plaid-api`): bank balances and transactions.
- **Printify** (`printify-api`): print-on-demand products and orders.
- **Ring** (`ring-api`): doorbell and camera events.
- **ServiceNow** (`servicenow-api`): IT tickets and service requests.
- **Spotify** (`spotify-api`): music playback and playlists.
- **Square** (`square-api`): payments and point of sale.
- **Tailscale** (`tailscale-api`): a private network and its devices.
- **Tessie** (`tessie-api`): car status and charging.
- **Threads** (`threads-api`): posts and replies.
- **Threads Messages** (`threads-messages-api`): direct messages.
- **Ticketmaster** (`ticketmaster-api`): event search and tickets.
- **Uber** (`uber-api`): rides.
- **WhatsApp** (`whatsapp-api`): chat messaging.
- **Withings** (`withings-api`): scale and blood-pressure readings.
- **Zendesk** (`zendesk-api`): help-desk tickets.

#### Not Connected
- Her newsletter platform, her CRM, the video-call tools and her listing-site hosting are handled by Brittany and her contractors; the assistant hands her copy in chat or as files in the workspace.
- Any app that is not listed under Connected Services is not connected to this assistant.
- Signed-in and interactive web access: `text-browser` reads public pages as plain text only. It cannot log in, submit forms, or run JavaScript, and blocked domains are refused, so account portals and sites that need a sign-in stay out of reach.
- Stellar MLS and the SunCoast CRM are separate institutional systems and are not connected to the assistant.
- Eric's, Carmen's, and the kids' private personal accounts are off limits unless Brittany explicitly grants access.
- Moving money or placing live trades through personal banking and brokerage accounts is not available; the tools above verify and track balances only.

### Built-in Tools

- **Text browser** (skill `text-browser`, script `scripts/browse.py`): reads public web pages as text through the harness gateway. `browse.py open "<url>"` returns the page text and its links, page by page (`--page N`); `browse.py find "<url>" "<pattern>"` returns the lines that match. It is the only route to the web from this workspace: `curl` or `wget` to a public site cannot resolve the host. It does not run JavaScript and cannot sign in, so JSON and plain-text endpoints and server-rendered pages work best; blocked domains are refused. Use it for links that appear in the connected data.
- **Image generation** (skill `image-generation`, script `scripts/generate_image.py`): makes new images from a text prompt, `generate_image.py "<prompt>" --out <path prefix> --format png [--size WxH] [--n N]`, and `--info` shows how many images this task may still request. It never edits an existing image and must not be asked to draw text or logos: typeset text and composite logos afterwards with Pillow, which `python3` has, using the DejaVu Sans fonts in `/usr/share/fonts/truetype/dejavu/`, and resize to the size the brief asks for.
