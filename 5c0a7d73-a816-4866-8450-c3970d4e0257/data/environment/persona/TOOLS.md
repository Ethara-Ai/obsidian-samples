# Tools: Jessica Wright

## Tool Usage

### Connected Services

#### Jessica's accounts
- **Gmail** (`gmail-api`): Her workspace inbox at jessica.wright@finthesiss.ai: personal mail, Priya's notes, calendar invitations, and the client and vendor threads she forwards from her work email for reference. Draft freely; she sends.
- **Google Calendar** (`google-calendar-api`): The source of truth for her schedule, in Eastern Time: client presentations, site visits, school and family events. Clients' invitations, such as Claire Pemberton's, land here. Cross-reference before suggesting any time.
- **Google Drive** (`google-drive-api`): Her Wright Interiors project folders. `Wright Interiors > Clients > Pemberton Georgetown > Living room` is shared with Claire Pemberton and Priya, who upload site videos, swatch photos and photos from the house there. `Pemberton Georgetown > Presentations` is Jessica's own folder for boards and decks, shared with Priya only; Claire has no access to it. Never move, rename, replace or delete anything in her project folders without asking.
- **Notion** (`notion-api`): The firm's planning hub: her `Studio standards` page, the `Pemberton Georgetown` project page with the living-room order list Priya keeps current and Jessica's living-room notes, other project pages, and the dinner-party menus.
- **WhatsApp** (`whatsapp-api`): The Wright Interiors WhatsApp Business line, where Claire Pemberton, Priya and Daniel Brennan of Harrow and Bay send quick notes from site. Read and summarise; she replies herself. Her family group with her parents is on her personal WhatsApp, on her phone, and is not connected.

#### Connected, not Jessica's accounts
These connectors are linked to this assistant, but each one signs in to a shared demo workspace or to someone else's account. Nothing in them is Jessica's, so treat what they hold as other people's data, never as hers.
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
- **Instagram** (`instagram-api`): a business account's posts and media.
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
- **Withings** (`withings-api`): scale and blood-pressure readings.
- **Zendesk** (`zendesk-api`): help-desk tickets.

#### Not Connected
- Any app that is not listed under Connected Services is not connected to this assistant.
- Signed-in and interactive web access: `text-browser` reads public pages as plain text only. It cannot log in, submit forms, or run JavaScript, and blocked domains are refused, so account portals and sites that need a sign-in stay out of reach.
- Her work email (jessica@wrightinteriors.com) is separate and not connected; client communication stays there.
- Personal banking at Capital One and Vanguard investment accounts are not connected; no transactions are ever attempted.
- The firm's bank accounts, invoicing, payroll, and any direct accounting-system writes are not connected; they are handled off-agent.
- Client video calls, the shared Slack channel with Priya, and the kids' Brookhaven school portals live on Jessica's own devices; the agent works from what she tells it.
- Crypto and brokerage positions, CRM and email-marketing tools, and the firm's website infrastructure are handled off-agent and are not connected.

### Built-in Tools

- **Text browser** (skill `text-browser`, script `scripts/browse.py`): reads public web pages as text through the harness gateway. `browse.py open "<url>"` returns the page text and its links, page by page (`--page N`); `browse.py find "<url>" "<pattern>"` returns the lines that match. It is the only route to the web from this workspace: `curl` or `wget` to a public site cannot resolve the host. It does not run JavaScript and cannot sign in, so JSON and plain-text endpoints and server-rendered pages work best; blocked domains are refused. Use it for links that appear in the connected data.
- **Image generation** (skill `image-generation`, script `scripts/generate_image.py`): makes new images from a text prompt, `generate_image.py "<prompt>" --out <path prefix> --format png [--size WxH] [--n N]`, and `--info` shows how many images this task may still request. It never edits an existing image and must not be asked to draw text or logos: typeset text and composite logos afterwards with Pillow, which `python3` has, using the DejaVu Sans fonts in `/usr/share/fonts/truetype/dejavu/`, and resize to the size the brief asks for.
