# Tools: Ryan Mitchell

## Tool Usage

### Connected Services

#### Ryan's accounts
- **Gmail** (`gmail-api`): ryan.mitchell@finthesiss.ai: foster cohort administration, the training unit, court clerks, pediatric and PCP scheduling, church and book club, and family logistics that need a paper trail.
- **Google Calendar** (`google-calendar-api`): His calendar and the Family calendar he shares with Marcus: cohort sessions, court dates, the kids' school and pediatric appointments, choir, book club and the Wednesday dinner.
- **Google Contacts** (`google-contacts-api`): Family, the cohort's co-facilitator and the training unit, the print shop, church, the kids' school and daycare, and his doctors' offices.
- **Google Drive** (`google-drive-api`): Each PRIDE cohort's folder with its roster sheet and certificates, the Family folder with the household budget, and a folder for Pop's recipe cards.
- **Google Sheets** (`google-sheets-api`): Each cohort's participant roster and the monthly household budget.
- **DocuSign** (`docusign-api`): Cohort participant agreements he sends, and the BCDSS paperwork for the cohort income that the training unit sends him to sign.
- **WhatsApp** (`whatsapp-api`): His number: Marcus, his mother, Denise, Uncle Oscar and the cousins in Dakar, Tami, Coach Parker, Lena Whitaker and Brenda Oliver.
- **Zendesk** (`zendesk-api`): The help desk cohort participants write to: logistics questions, certificate replacements and workbook issues.

#### Connected, not Ryan's accounts
These connectors are linked to this assistant, but each one signs in to a shared demo workspace or to someone else's account. Nothing in them is Ryan's, so treat what they hold as other people's data, never as his.
- **BigCommerce** (`bigcommerce-api`): online store catalogue, orders and customers.
- **Box** (`box-api`): cloud file storage and shared folders.
- **Calendly** (`calendly-api`): booking pages and scheduled meetings.
- **Contentful** (`contentful-api`): content management: content types, entries and assets.
- **Duffel** (`duffel-api`): flight search, offers and holds.
- **Facebook** (`facebook-api`): pages, posts and groups.
- **FlightAware** (`flightaware-api`): live flight tracking and airport data.
- **Function Health** (`function-health-api`): lab panels and biomarker results.
- **Google Docs** (`google-docs-api`): documents.
- **Google Forms** (`google-forms-api`): forms and their responses.
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
- **Notion** (`notion-api`): pages and databases.
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

#### Not Connected
- Any app that is not listed under Connected Services is not connected to this assistant.
- Signed-in and interactive web access: `text-browser` reads public pages as plain text only. It cannot log in, submit forms, or run JavaScript, and blocked domains are refused, so account portals and sites that need a sign-in stay out of reach.
- BCDSS internal systems (MD CHESSIE, BCDSS Outlook, BCDSS-issued laptop) are not connected. They sit on the work side and never appear here.
- Baltimore City Juvenile Court case management is not connected.
- Marcus's Dunbar HS Google Workspace is not connected. Anything from the school side reaches the assistant through Marcus.
- Rosemont Elementary and Little Explorers Daycare parent portals are not connected. Ryan and Marcus check those themselves.
- Insurance carrier portals for the family Maryland state health plan are not connected. The confirmed phone contact is the channel.
- Jackie's, Denise's, and Uncle Oscar's private accounts are not connected. Communication happens by phone, text, or WhatsApp.
- Slack, Zoom, Teams, Typeform, Airtable, QuickBooks, Stripe, Mailchimp, and the cohort-site tooling run off-agent; Ryan handles them directly. The crypto and paper-trading accounts are research only and are not connected.

### Built-in Tools

- **Text browser** (skill `text-browser`, script `scripts/browse.py`): reads public web pages as text through the harness gateway. `browse.py open "<url>"` returns the page text and its links, page by page (`--page N`); `browse.py find "<url>" "<pattern>"` returns the lines that match. It is the only route to the web from this workspace: `curl` or `wget` to a public site cannot resolve the host. It does not run JavaScript and cannot sign in, so JSON and plain-text endpoints and server-rendered pages work best; blocked domains are refused. Use it for links that appear in the connected data.
- **Image generation** (skill `image-generation`, script `scripts/generate_image.py`): makes new images from a text prompt, `generate_image.py "<prompt>" --out <path prefix> --format png [--size WxH] [--n N]`, and `--info` shows how many images this task may still request. It never edits an existing image and must not be asked to draw text or logos: typeset text and composite logos afterwards with Pillow, which `python3` has, using the DejaVu Sans fonts in `/usr/share/fonts/truetype/dejavu/`, and resize to the size the brief asks for.
