# Customer Messaging Guidelines

> **PROTOTYPE MATERIAL — NOT REAL BANK COMMUNICATIONS POLICY.**
> This document is fictional, written for the Novamind fraud-detection prototype.
> All guidelines are invented for demonstration purposes.
> Do not use this as a substitute for real communications compliance review.

---

## 1. Purpose

This document governs the exact words and structure of in-app questions the Engagement Agent sends to the customer when a transaction requires verification. It is also referenced by the Risk Agent when deciding whether a draft question is appropriate to send.

---

## 2. Core Principles

| Principle | Rule |
|---|---|
| **Calm** | No urgency words. The customer should feel reassured, not panicked. |
| **Plain language** | No jargon, acronyms, or technical terms. Write as if speaking to someone who is busy. |
| **One question** | Ask exactly one yes/no question per message. No compound questions. |
| **Short** | The full message — greeting, context, and question — must be **under 40 words**. |
| **Personal** | Use only details from the customer's own transaction history. Do not use generic language. |
| **No links** | Never include a URL, a deep link, or any tappable element beyond the Yes/No buttons. |
| **No urgency words** | Prohibited words: "immediately", "urgent", "critical", "suspended", "locked", "arrested", "penalty", "expire". |
| **No codes or credentials** | Never ask the customer for a PIN, password, one-time code, or any authentication value. |

---

## 3. Message Structure

A well-formed in-app question has three parts, all within the 40-word limit:

```
[Context sentence: one fact from their history, e.g. their usual merchant or amount]
[Question: "Was this you?"]
[Response options: Yes / No — rendered as buttons, not asked in text]
```

The response options ("Yes, that was me" / "No, that wasn't me") are rendered as tappable buttons by the app UI. The Engagement Agent only produces the text; the buttons are added by the app.

---

## 4. Examples

### 4.1 Good Examples

**Scenario:** NorthSide Supply, new terminal, $340.

> "We saw a $340 payment to NorthSide Supply just now — different reader than usual.
> Was this you?"

Word count: 19. ✅ Calm. ✅ One question. ✅ Uses customer's merchant. ✅ No link. ✅ Under 40 words.

---

**Scenario:** Unknown merchant, moderate amount, $295.

> "A $295 charge appeared at ElectroParts Depot — a shop you haven't used before.
> Was this you?"

Word count: 18. ✅ Calm. ✅ Factual. ✅ No urgency. ✅ No link. ✅ Under 40 words.

---

**Scenario:** Overseas CNP — this is a High-risk scenario so no question is sent; the message below is for a case where the agent has already held and is notifying the customer, not asking.

> "We've temporarily held a $1,950 charge from Hong Kong.
> We'll be in touch shortly."

Word count: 16. ✅ Informational only. ✅ No ask. ✅ No link.

---

### 4.2 Bad Examples — Do Not Use

❌ **Too urgent:**
> "URGENT: Your account may be at risk. A suspicious transaction has been detected. Tap here IMMEDIATELY."

Problems: urgency words ("URGENT", "IMMEDIATELY"), link ("Tap here"), no specific details.

---

❌ **Link included:**
> "Please verify this charge: https://bank.example.com/verify?txn=12345"

Problems: contains a URL; the customer cannot distinguish this from a phishing link.

---

❌ **Compound question:**
> "Was this you, or did someone else use your card, and should we block it?"

Problems: three questions in one sentence; the customer does not know which one to answer.

---

❌ **Asks for credentials:**
> "To confirm this was you, please reply with your PIN."

Problems: never ask for credentials in any channel.

---

❌ **Generic — no personal detail:**
> "We noticed unusual activity on your account. Please confirm."

Problems: no merchant name, no amount, no specific detail — indistinguishable from a scam message.

---

❌ **Discloses detection detail:**
> "Your transaction scored 45 on our risk model because it fired the new_terminal_known_merchant signal."

Problems: discloses score and signal name. Fraudsters can use this to calibrate attacks.

---

## 5. What May and May Not Be Included

### 5.1 Allowed in the question text:

- The merchant name (as it appears in the customer's own history)
- The approximate amount of the transaction
- A brief contextual observation from the customer's history (e.g. "a shop you haven't used before", "different reader than usual", "a bit higher than your usual amount there")
- The day or time if it is specifically anomalous and clearly based on the customer's own pattern

### 5.2 Prohibited in the question text:

| Prohibited item | Why |
|---|---|
| URLs or links of any kind | Indistinguishable from phishing; customer has been trained never to tap bank links |
| Urgency words ("immediately", "urgent", "critical") | Creates panic; increases susceptibility to further social engineering |
| Detection thresholds or score values | Enables fraudsters to calibrate attacks to stay below thresholds |
| Signal names (e.g. "velocity_spike", "unusual_hour") | Technical jargon; also reveals detection logic |
| The phrase "your account is locked" or "your account has been suspended" | Directly mirrors the language fraudsters use in scam calls |
| Requests for PINs, passwords, codes, or OTPs | Violates basic security hygiene |
| References to a phone call or a "bank agent" | Validates the scammer's cover story if the customer is currently being coached |
| Details a fraudster could look up (e.g. branch address, account number) | Useful to a social engineer confirming they have the right victim |

---

## 6. Retry Message (Second Channel — Push Notification)

If no reply is received within 15 minutes, a push notification is sent. The push notification:

- Must be **even shorter** than the in-app question (10–15 words maximum).
- Must not contain account details (no amount, no merchant name in the push title/body — these are visible on lock screens).
- Must direct the customer to open the banking app, not to a URL.

**Good retry push:**
> "We sent you a question in the Novamind app. Please open it to respond."

**Bad retry push:**
> "⚠️ URGENT: Your $340 NorthSide Supply payment is on hold. Tap here to unblock."

Problems with bad example: urgency emoji, urgency word, amount and merchant name visible on lock screen, contains a link.

---

## 7. Tone Reference

The correct emotional register is: **reassuring and matter-of-fact**, the same tone a helpful bank employee would use if they called and said, "Hi, I'm just checking — did you make a payment just now?"

Avoid the tone of:
- A security alert (too alarming)
- A marketing message (too friendly)
- A legal notice (too formal)
- A robocall script (too mechanical)

---

## Sources

Synthetic policy written for the Novamind prototype, informed by public consumer-protection guidance.
