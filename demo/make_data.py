"""Generate the demo's feedback for Capital Bank of Australia, a fictional bank, dated in the current window.

Usage (from the repository root):  python3 demo/make_data.py

Writes two different data sets that tell one story, into profiles/demo/data/ where the demo profile reads them
(not committed; run this before a demo):
  tickets.csv   customer support tickets from the helpdesk (no rating)
  survey.csv    in-app survey comments with a 0 to 10 score (the internal warehouse data)
The same files feed the live connections: load_zendesk.py imports the tickets into a Zendesk account, and
load_warehouse.py loads the survey into BigQuery. Capital Bank of Australia, its customers and every message are fictional.
"""
import csv, datetime, os, random

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles", "demo")  # the demo profile's folder
rng = random.Random(7)
TODAY = datetime.date.today()
CITIES_NORTH = ["Brisbane", "Gold Coast", "Townsville", "Cairns", "Toowoomba", "Sunshine Coast"]  # where the transfer delays cluster
CITIES = CITIES_NORTH + ["Sydney", "Melbourne", "Perth", "Adelaide", "Hobart", "Canberra"]
DISHES = ["the supermarket", "a petrol station", "an online store", "a cafe", "the chemist", "a hotel overseas",
          "my electricity bill", "a rideshare", "the airport", "a hardware store"]  # merchants
ITEMS = ["my rent", "my pay", "a transfer to my sister", "the deposit for a car", "a payment to my landlord",
         "money to my savings account", "the school fees", "a BPAY bill", "an invoice", "my mortgage repayment"]
OPEN = ["", "Hi, ", "Hello, ", "Hi team, ", "", "Good morning, "]
SURVEY_OPEN = ["", "", "Honestly, ", "Overall ", "To be fair, ", "Mostly happy. ", "Mixed week. ", "Quick note: ", "As a long time customer, "]
CLOSE = ["", " Please fix this urgently.", " Not happy.", " Can someone call me?", " Thanks.", "", " This is the second time."]

# (theme, share of tickets, share of survey, which days: "late" = the second half of the window, "all" = any day)
THEMES = {
    "declined": (0.26, 0.14, "late"),
    "login": (0.20, 0.14, "late"),
    "transfers": (0.18, 0.10, "all"),
    "fees": (0.14, 0.10, "all"),
    "scams": (0.08, 0.04, "all"),
    "praise": (0.02, 0.26, "all"),
    "requests": (0.04, 0.16, "all"),
    "other": (0.08, 0.06, "all"),
}

TICKET = {
    "declined": [("Card declined", "My debit card was declined at {dish} on {day} even though I have plenty of money in the account."),
                 ("Card keeps getting declined", "Third time this week my card has been declined at {dish}. The app says the payment was blocked as suspicious."),
                 ("Payment blocked", "A normal purchase at {dish} was blocked and my card was frozen. I had to call to unfreeze it."),
                 ("Declined overseas", "My card was declined at {dish} while travelling, I had told the bank I was going away."),
                 ("Fraud block on everyday purchases", "Since {day} every second tap at {dish} gets declined for fraud checks.")],
    "login": [("Can't log in", "Since the app updated to 6.1 I can't log in, it says my code has expired before it even arrives."),
              ("Not receiving security codes", "I'm not getting the SMS verification code so I'm locked out of the app."),
              ("Locked out of the app", "The app crashes on the fingerprint screen after the latest update and then locks me out."),
              ("Two factor not working", "The two factor code never works on the first try, I have to request it four or five times.")],
    "transfers": [("Transfer delayed", "I sent {item} on {day} and it still hasn't arrived. It was meant to be instant."),
                  ("Payment not received", "{item} left my account but the other bank says nothing has arrived."),
                  ("Where is my money?", "A transfer I made in {north} on {day} is showing as pending for two days."),
                  ("Late payment caused a fee", "Because {item} arrived a day late I was charged a late fee by my landlord.")],
    "fees": [("Unexpected fee", "I was charged an overdraft fee even though my pay was due the same day."),
             ("Foreign transaction fee", "I was charged a foreign transaction fee on a purchase from {dish}, I thought this card had none."),
             ("Fee not explained", "There is a monthly account fee on my statement that I was never told about."),
             ("Charged twice", "I was charged the same fee twice on {day}.")],
    "scams": [("Suspicious text message", "I got a text claiming to be Capital Bank asking me to confirm my details through a link."),
              ("Scam call", "Someone called pretending to be from your fraud team and asked for my security code. I hung up but want to report it."),
              ("I think I was scammed", "I paid what I thought was an invoice and now I think it was a scam. Please help me get the money back."),
              ("Fake website", "There is a website that looks exactly like your login page, I nearly entered my details.")],
    "praise": [("Thank you", "Just wanted to say the staff at the {north} branch were brilliant when I set up my account.")],
    "requests": [("Joint account", "Can I open a joint account with my partner in the app? I can't find the option.")],
    "other": [("Change of address", "How do I update my address after moving?"),
              ("Statement request", "I need a statement for the last six months for a rental application."),
              ("Card replacement", "My card is worn out, how do I order a new one?")],
}
SURVEY = {
    "declined": ["My card keeps getting declined for no reason.", "The fraud checks are blocking normal purchases at {dish}.",
                 "Card declined twice this week, embarrassing at the checkout.", "Too many false fraud alerts lately."],
    "login": ["Logging in has been a nightmare since the update.", "Security codes take forever to arrive.",
              "The app crashes at the fingerprint login.", "Locked out again, the two factor codes don't work."],
    "transfers": ["Transfers are slower than they used to be.", "{item} took two days to arrive.", "Instant payments aren't instant any more."],
    "fees": ["Fees are confusing and not explained.", "Got charged a fee I didn't expect.", "Please be clearer about overdraft fees."],
    "scams": ["I've had a few scam texts pretending to be you, please warn customers.", "Worried about scam calls using the bank's name."],
    "praise": ["The app is easy to use and the spending insights are great.", "Instant notifications for every purchase are really useful.",
               "Branch staff in {north} were very helpful.", "Love being able to freeze my card in the app.",
               "Customer service sorted my issue quickly.", "Best banking app I've used."],
    "requests": ["Please add savings goals in the app.", "Would like to open a joint account online.", "Would love Apple Pay support for my card.",
                 "Please add a budgeting feature."],
    "other": ["Would like more branches open on Saturdays.", "The website could be easier to navigate.", "Statements are hard to find."],
}
EXTRA = {
    "declined": ["I had to use another card.", "The app said it was blocked as suspicious.", "It's happened three times now.",
                 "I had to call to unfreeze my card.", "My partner has the same problem.", "Nothing about my spending has changed."],
    "login": ["I'm on an iPhone.", "Reinstalled the app, still broken.", "The website login works though.", "I've missed a bill because of it.",
              "Waited twenty minutes for a code."],
    "transfers": ["The reference was correct.", "I need it sorted today.", "The app shows it as completed.", "It used to arrive in seconds."],
    "fees": ["Please refund it.", "I've been a customer for years.", "Nothing in the app warned me.", "This is really frustrating."],
    "scams": ["I didn't click the link.", "I've kept the message.", "Please warn other customers.", "It looked very convincing."],
    "praise": ["Will definitely recommend.", "Five stars from me.", "Much better than my old bank.", "Keep it up."],
    "requests": ["Other banks already have this.", "Would use it every week.", "Happy to test it."],
    "other": ["Couldn't find it in the help centre.", "Thanks in advance.", "No rush."],
}
SCORE = {"declined": (1, 5), "login": (0, 4), "transfers": (2, 6), "fees": (1, 5), "scams": (3, 7), "praise": (8, 10),
         "requests": (6, 9), "other": (6, 9)}


def day_for(when):
    lo = 3 if when == "late" else 0  # "late" themes start in the second half of the window
    return TODAY - datetime.timedelta(days=rng.randint(0, 6 - lo))


def fill(text, d, theme):
    if rng.random() < 0.75:
        text += " " + rng.choice(EXTRA[theme])
    if rng.random() < 0.4:
        text += " " + rng.choice([x for x in EXTRA[theme] if x not in text])
    return text.format(day=d.strftime("%A"), north=rng.choice(CITIES_NORTH), dish=rng.choice(DISHES),
                       item=rng.choice(ITEMS), item2=rng.choice(ITEMS))


def join(opener, text):
    """An opener ending in a comma runs into the sentence, so its first word is lower case."""
    if opener.endswith(", ") and not text.startswith(("I ", "I'")):
        text = text[0].lower() + text[1:]
    return opener + text


def build(templates, share_index, n, survey=False):
    rows = []
    for theme, spec in THEMES.items():
        for _ in range(round(n * spec[share_index])):
            d = day_for(spec[2])
            if survey:
                text = join(rng.choice(SURVEY_OPEN), fill(rng.choice(templates[theme]), d, theme))
                rows.append({"date": d.isoformat(), "score": rng.randint(*SCORE[theme]), "comment": text,
                             "city": rng.choice(CITIES_NORTH if theme == "transfers" else CITIES)})
            else:
                subject, body = rng.choice(templates[theme])
                rows.append({"date": d.isoformat(), "subject": subject, "description": join(rng.choice(OPEN), fill(body, d, theme)) + rng.choice(CLOSE),
                             "channel": rng.choice(["phone", "chat", "email", "branch"])})
    rng.shuffle(rows)
    return rows


os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
tickets = build(TICKET, 0, 260)
survey = build(SURVEY, 1, 240, survey=True)
with open(os.path.join(HERE, "data", "tickets.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, ["ticket_id", "created_at", "subject", "description", "channel"])
    w.writeheader()
    for n, r in enumerate(tickets, 1001):
        w.writerow({"ticket_id": n, "created_at": r["date"], "subject": r["subject"], "description": r["description"], "channel": r["channel"]})
with open(os.path.join(HERE, "data", "survey.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, ["response_id", "submitted_at", "score", "comment", "city"])
    w.writeheader()
    for n, r in enumerate(survey, 1):
        w.writerow({"response_id": f"s{n:04d}", "submitted_at": r["date"], "score": r["score"], "comment": r["comment"], "city": r["city"]})
print(f"wrote {len(tickets)} tickets and {len(survey)} survey responses, dated {TODAY - datetime.timedelta(days=6)} to {TODAY}")
