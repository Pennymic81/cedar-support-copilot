# 2-minute demo script

Record your screen with the live Render site open. Have two tabs ready: the demo site (`/`) and the dashboard (`/dashboard/`, logged in as `admin`). Open the site once before recording, because the free plan sleeps and the first load takes about a minute.

---

**0:00 – 0:15 · The problem** (demo site on screen)

> "Support teams answer the same questions all day, and in fintech a chatbot that guesses about someone's money does more harm than good. I built an AI support copilot that only answers from the company's own policies, and hands anything risky to a person. Cedar Pay here is a fictional demo brand. The copilot is the product."

**0:15 – 0:40 · A sourced answer** (open the chat bubble)

Type: **How long does a transfer to Spain take?**

> "It finds the right policy section and answers from it, and you can see the source under the answer: Fees and transfer times, Transfer times. Nothing comes from outside the company's docs."

**0:40 – 1:05 · The money-safety handoff**

Type: **I was charged $250 but the transfer failed. Where is my money?**

> "This one involves the customer's money, so it never gets an AI answer, even though there's a matching policy. It goes straight to a person."

Then type: **Do you offer car loans?** (optional, if time allows)

> "And when nothing in the docs matches, it says so and hands off instead of making something up."

**1:05 – 1:30 · The team's side** (switch to `/admin/support/ticket/` or show the ticket via the API)

> "On the team's side, the ticket arrives with a summary and a drafted reply built only from the reversals policy, with its source. The agent can approve it, edit it, or write their own, and that choice is tracked."

**1:30 – 1:50 · Measured, not guessed** (switch to the dashboard)

> "This dashboard shows how support is going: how much the AI resolves, why chats were handed off, and what customers ask about most. These conversations are demo traffic. The eval runs are real: 38 test questions run through the pipeline after every change. The first run caught two unsafe answers; I fixed the rules and tuned the threshold until it reached zero."

**1:50 – 2:00 · Close**

> "It's built with Django, Postgres with pgvector, 73 automated tests and an eval suite, and deploys to Render in one click. The code is on GitHub at Pennymic81/cedar-support-copilot. Thanks for watching."

---

Tips: zoom the browser to 125% so text is readable, type the questions in advance to paste them, and keep the cursor still while you talk.
