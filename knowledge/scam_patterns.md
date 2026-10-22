# Scam Patterns Reference

> **PROTOTYPE MATERIAL — NOT OPERATIONAL INTELLIGENCE.**
> This document is fictional, written for the Novamind fraud-detection prototype.
> Pattern descriptions are generalised from publicly available reports (sources listed below).
> Do not use this document as a substitute for real fraud-intelligence feeds.

---

## How to Use This Document

The Risk Agent consults this document via RAG to match incoming signal combinations against known fraud patterns. Each pattern lists: the signals it typically fires, the typical transaction amount range, and the recommended system response level.

---

## Pattern 1 — Bank Impersonation Text with Link

**Description:** Customer receives an SMS or in-app message that appears to come from their bank, contains a link, and instructs them to "verify" or "unblock" their account. The link leads to a phishing page that harvests credentials or card details. The fraudster then uses those details to initiate a card-not-present transaction.

**Signals in transaction data:**
- `card_not_present` channel, shortly after the customer would have received the SMS
- New merchant, new MCC
- Transaction time may be unusual (outside customer's normal hours)

**Typical amounts:** $150 – $2,000 (test charge first, then larger)

**Recommended response level:** Moderate to High (score ≥ 40 if CNP + new merchant; ≥ 70 if amount is also above P90)

**Note for engagement agent:** Do NOT send a link in the in-app question. The customer has just been tricked by a link; another link, even a real one, will increase confusion and distrust.

---

## Pattern 2 — "Your Account Is Locked" Voice Call

**Description:** Fraudster calls the customer, poses as the bank's fraud team, claims the account is locked, and pressures the customer to "approve" a transaction on their phone to "re-verify" their identity. Customer is kept on the phone during the approval — a key pressure tactic.

**Signals in transaction data:**
- Moderate-amount transaction, known or unknown merchant
- Rapid sequence of approval attempts (customer is on the phone being coached)
- May trigger the 3-approvals-in-24h edge rule

**Typical amounts:** $200 – $5,000

**Recommended response level:** High if 3+ approvals in 24 h. Escalate immediately. Do not release any hold while the customer appears to be in a live approval loop.

**Note for engagement agent:** Keep the question to one factual check ("Did you make a $340 payment to NorthSide Supply just now?"). Do not mention a phone call or a "bank agent", as that is exactly what the fraudster has told the customer.

---

## Pattern 3 — Overseas Card-Not-Present Probe

**Description:** A stolen card number is tested with a low-value CNP charge in a foreign currency or from a foreign merchant, followed quickly by a higher-value charge if the first is not declined. The low-value probe is often under $10 and at an obscure merchant.

**Signals in transaction data:**
- `card_not_present` channel
- Foreign country or city not in customer history
- New merchant, unfamiliar MCC (often electronics, digital goods, or gift cards)
- Amount at or just below a round number threshold

**Typical amounts:** Probe: $1 – $15. Follow-on: $300 – $3,000

**Recommended response level:** High for CNP + overseas + new merchant combination (fires `card_not_present_overseas` signal, weight 50). Immediate partial hold; do not wait for customer reply before holding.

---

## Pattern 4 — Small Test Charge Preceding a Large One

**Description:** Fraudster runs a $1 – $5 authorisation to confirm the card is live, then submits the real charge within minutes to hours. The test charge may go to a different merchant than the large charge.

**Signals in transaction data:**
- Two or more transactions in a short window (< 2 hours)
- First transaction is unusually small (well below customer's P10)
- Second transaction is at or above customer's P90
- Terminal or merchant may differ between the two

**Typical amounts:** Test: $1 – $5. Main charge: $500 – $4,000

**Recommended response level:** Moderate if only one of the two is present; High if both appear within 2 hours (`velocity_spike` signal, weight 45, combined with `amount_above_p90`, weight 20).

---

## Pattern 5 — Merchant Terminal Swap

**Description:** Fraudster installs a skimming overlay or replaces a legitimate point-of-sale terminal at a merchant the customer regularly uses. The card details are captured and used to create a counterfeit card or CNP transaction. The fraudulent charge appears at the same merchant but with a different terminal ID.

**Signals in transaction data:**
- Known merchant, but new terminal ID (`new_terminal_known_merchant` signal, weight 30)
- Amount may be consistent with customer's normal spending at that merchant
- Time of day consistent with customer's normal visit window

**Typical amounts:** Matches customer's usual range for that merchant

**Recommended response level:** Moderate (score ≈ 30). Ask the customer. If they confirm it was them, add the terminal to baseline. If not, hold and open case.

---

## Pattern 6 — Account Takeover Followed by Rapid Transfers

**Description:** Fraudster gains access to online banking (via phishing, credential stuffing, or SIM swap) and immediately initiates a series of transfers to mule accounts, often before the customer notices. Transfers may mimic the customer's normal payee list to avoid simple rule triggers.

**Signals in transaction data:**
- Multiple transfers in a short window (< 1 hour), firing `velocity_spike`
- Payees may be new merchants or new transfer accounts not in customer's history
- Amounts often at or near the customer's daily transfer limit
- Transaction time may be unusual (early morning or late night)

**Typical amounts:** $500 – $10,000 per transfer; multiple in rapid succession

**Recommended response level:** High if velocity spike + new payee + unusual hour all fire together (combined score likely ≥ 70). Immediate partial hold; open case; queue analyst.

---

## Pattern 7 — Social Engineering — Approve While on the Phone

**Description:** Variant of Pattern 2. The fraudster keeps the customer on the phone and instructs them to approve each "security test" transaction as it appears in their app, claiming each one will be immediately reversed. The customer approves 3+ transactions in a row.

**Signals in transaction data:**
- 3 or more "that was me" approvals in < 24 hours (triggers the rapid-approval edge rule)
- Transactions may be to different merchants but of consistent amounts
- Customer responds quickly to each in-app question (coached responses)

**Typical amounts:** $100 – $1,500 per transaction; multiple in a session

**Recommended response level:** Escalate on the third approval. The 3-approvals-in-24h rule is specifically designed for this pattern. Do not release the third hold. Queue analyst immediately.

---

## Pattern 8 — Gift Card Drain

**Description:** Fraudster convinces the customer to purchase gift cards (often via social engineering: "pay a debt", "avoid arrest") and share the codes. Alternatively, stolen card details are used to buy gift cards directly. Gift card MCCs are specific and easy to flag.

**Signals in transaction data:**
- New merchant or known gift-card retailer (MCC 5947, 5999, or 6211)
- Amount just below a round threshold (e.g. $499 rather than $500)
- May be repeated multiple times in a day

**Typical amounts:** $50 – $500 per card; often 2-5 cards in a session

**Recommended response level:** Moderate if single transaction (new merchant + amount pattern); High if repeated in a short window (`velocity_spike` fires). Always ask if MCCs 5947/5999/6211 appear for the first time.

---

## Pattern 9 — Charity or Invoice Scam

**Description:** Fraudster sends a fake invoice or charity donation request, often spoofing a real business the customer has previously transacted with. Customer believes they are paying a legitimate invoice.

**Signals in transaction data:**
- Transfer to a new payee, or CNP to a new merchant in a known category (MCC 8398 or 8049)
- Amount consistent with customer's invoicing patterns but payee never seen before
- Transaction time may be during normal business hours (not an unusual signal alone)

**Typical amounts:** $150 – $5,000

**Recommended response level:** Moderate (new payee + amount check). Ask the customer: "Did you recently receive an invoice from [payee name]?"

---

## Pattern 10 — Velocity Spike on a Compromised Card

**Description:** Card details are stolen and used to make many small purchases at varied online merchants in a short time window before the card is declined or cancelled. Each individual transaction may be below alert thresholds but the velocity together is anomalous.

**Signals in transaction data:**
- 4+ transactions within 2 hours
- Mix of known and new merchants
- CNP channel
- `velocity_spike` signal fires (weight 45)

**Typical amounts:** $10 – $200 per transaction; many in rapid succession

**Recommended response level:** High if velocity_spike fires with CNP. Partial hold on the cluster; open case; queue analyst.

---

## Pattern 11 — Refund Fraud / Overpayment Scam

**Description:** Fraudster contacts the customer (posing as tech support or a refund agent), gains remote access to their device, and engineers a "mistaken overpayment" scenario. Customer is convinced to send back funds via bank transfer to a mule account.

**Signals in transaction data:**
- Outbound transfer to a new payee, often rounded amount
- Transfer follows shortly after a card-not-present transaction from a tech-support category MCC (7372, 7371)
- Customer may have recent CNP transactions to remote-access software vendors

**Typical amounts:** Transfer: $500 – $10,000

**Recommended response level:** High if new-payee transfer follows a tech-category CNP in the same session. Immediate hold on the transfer; open case.

---

## Sources

Synthetic policy written for the Novamind prototype, informed by public consumer-protection guidance.
