# Add a Job Application — Prompt

Paste this whole file into a chat with an AI assistant (ChatGPT, Claude,
etc.) whenever you want to log a new job application into
`manual_applications.json`. Paste the current contents of your
`manual_applications.json` where indicated below before sending.

---

You are helping me maintain a JSON file called `manual_applications.json`
that tracks job applications I've submitted outside of my automated
Workday tracker. Each entry follows this schema:

```json
{
  "company": "Company Name",       // required
  "role": "Job Title",             // optional
  "date_applied": "YYYY-MM-DD",    // required
  "status": "Waiting"              // optional, defaults to "Waiting"
}
```

Here is my current list of tracked applications:

```json
<PASTE THE CURRENT CONTENTS OF manual_applications.json HERE>
```

I'm going to tell you about a job I applied to. Do the following:

1. Ask me for the company name and role, if I haven't already given both.
2. Check the current list above for any existing entry at the same
   company:
   - If there's an existing entry for the **same company and same role**,
     don't assume — ask me directly whether this is (a) a duplicate I
     already logged, (b) a genuine re-application (e.g. I reapplied after
     being rejected or the posting reopened), or (c) a mistake and I meant
     a different role.
   - If there's an existing entry for the **same company but a different
     role**, just confirm it's a separate role and proceed — no need to
     ask about duplicates.
   - If the company isn't in the list at all, treat it as new.
3. Ask for the date applied if I didn't give one (default to today's date
   if I don't know it).
4. Ask if there's a specific status other than the default `"Waiting"`
   (e.g. if I've already heard back).
5. Once you have enough information, output ONLY the new JSON object to
   add, formatted to match the schema above, plus the full updated JSON
   array with the new entry appended in the right place — ready for me to
   paste directly back into `manual_applications.json`.

Keep questions minimal — don't ask for anything I've already told you.
