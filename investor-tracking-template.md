# Investor Tracking Spreadsheet Template
**For Managing Your Fundraising Pipeline**

## Quick Setup Instructions

### Option 1: Copy This Template to Google Sheets
Create a new Google Sheet with these columns:

---

## Column Structure

| Investor Name | Firm/Type | Stage | Source | Status | First Contact | DocSend Link | Last View | Engagement Score | Next Step | Notes |
|---------------|-----------|-------|--------|--------|---------------|--------------|-----------|------------------|-----------|-------|
| Example: Sarah Chen | Array Ventures | Pre-Seed | Warm intro - John Smith | Meeting Scheduled | 2/1/26 | docsend.com/view/abc123 | 2/3/26 | 🔥 High | Call 2/10 @ 2pm | Loves infra plays |

---

## Column Definitions

### Basic Info
- **Investor Name**: Individual or firm name
- **Firm/Type**: VC firm name or "Angel Investor"
- **Stage**: Pre-seed, Seed, Angel, etc.

### Tracking
- **Source**: How you connected
  - Warm intro (from whom)
  - Cold email
  - OpenVC
  - Event/conference
  - Inbound
- **Status**: Current stage
  - Research
  - Outreach planned
  - Reached out
  - Deck sent
  - Meeting scheduled
  - Meeting completed
  - Follow-up
  - Passed
  - Committed
  - Closed

### Engagement Metrics
- **First Contact**: Date you first reached out
- **DocSend Link**: Which link version you sent
- **Last View**: Last time they opened your deck (from DocSend)
- **Engagement Score**:
  - 🔥 High (viewed 100%, 5+ min, returned 2+ times)
  - ⚠️ Medium (viewed 60-80%, 2-4 min)
  - ❌ Low (viewed <50%, <90 sec)
  - ⏳ Not yet viewed

### Next Actions
- **Next Step**: Specific action with date
- **Notes**: Key details, interests, objections, partner feedback

---

## Status Definitions & Actions

### Research
**What it means**: Identifying potential investors
**Action**: Add to list, no contact yet

### Outreach Planned
**What it means**: Warm intro being arranged or cold email drafted
**Action**: Request intro or schedule send

### Reached Out
**What it means**: Initial contact made, awaiting response
**Action**: Follow up in 5-7 days if no response

### Deck Sent
**What it means**: They requested materials
**Action**: Monitor DocSend analytics daily

### Meeting Scheduled
**What it means**: Call/meeting on calendar
**Action**: Prepare custom talking points based on their portfolio

### Meeting Completed
**What it means**: First meeting done
**Action**: Send thank you + any requested materials within 24 hours

### Follow-up
**What it means**: Ongoing dialogue, need more info/traction
**Action**: Send monthly updates with key metrics

### Passed
**What it means**: Declined to invest
**Action**: Ask for feedback, add to long-term nurture (follow up in 6 months)

### Committed
**What it means**: Verbal yes, term sheet signed
**Action**: Legal docs, close

### Closed
**What it means**: Money in bank
**Action**: Send thank you, add to investor update list

---

## Pre-Made Filters (Create in Google Sheets)

### Active Pipeline
- Status = "Reached out" OR "Deck sent" OR "Meeting scheduled" OR "Meeting completed" OR "Follow-up"

### Hot Leads (Need Immediate Attention)
- Engagement Score = 🔥 High
- Status ≠ "Passed" OR "Closed"

### Follow-up Needed
- Last View > 7 days ago
- Status = "Deck sent" or "Meeting completed"

### Warm Intro Success Rate
- Source = "Warm intro"
- Status = "Committed" or "Closed"

---

## Weekly Review Questions

### Monday Morning:
1. How many meetings this week?
2. Who viewed deck over the weekend?
3. Any follow-ups overdue?

### Friday Afternoon:
1. What's the commit:reach-out ratio?
2. Which investors need nurturing?
3. Any patterns in "Passed" reasons?

---

## Sample Entries for Reference

### Example 1: Warm Intro Success
| Investor Name | Firm/Type | Stage | Source | Status | First Contact | DocSend Link | Last View | Engagement Score | Next Step | Notes |
|---------------|-----------|-------|--------|--------|---------------|--------------|-----------|------------------|-----------|-------|
| Sarah Chen | Array Ventures | Pre-Seed | Warm intro - Mike at Acme | Meeting Scheduled | 2/1/26 | /view/array-intro | 2/3/26 | 🔥 High | Call 2/10 @ 2pm PT | Loves AI infra, ask about portfolio co synergies |

### Example 2: Cold Email - No Response
| Investor Name | Firm/Type | Stage | Source | Status | First Contact | DocSend Link | Last View | Engagement Score | Next Step | Notes |
|---------------|-----------|-------|--------|--------|---------------|--------------|-----------|------------------|-----------|-------|
| John Park | Betaworks | Pre-Seed | Cold email | Reached out | 2/1/26 | /view/cold-batch1 | Never | ⏳ Not viewed | Follow up 2/8 | Sent to general email, may need partner-specific |

### Example 3: Strong Interest
| Investor Name | Firm/Type | Stage | Source | Status | First Contact | DocSend Link | Last View | Engagement Score | Next Step | Notes |
|---------------|-----------|-------|--------|--------|---------------|--------------|-----------|------------------|-----------|-------|
| Alex Rivera | Root Ventures | Seed | OpenVC match | Follow-up | 1/25/26 | /view/root | 2/5/26 | 🔥 High | Send product roadmap by 2/7 | Wants to see 3-mo plan, considering lead |

### Example 4: Passed with Feedback
| Investor Name | Firm/Type | Stage | Source | Status | First Contact | DocSend Link | Last View | Engagement Score | Next Step | Notes |
|---------------|-----------|-------|--------|--------|---------------|--------------|-----------|------------------|-----------|-------|
| Maria Lopez | Pioneer Fund | Pre-Seed | YC network | Passed | 1/20/26 | /view/pioneer | 1/28/26 | ⚠️ Medium | Nurture - follow up in 6mo | Too early, wants to see $10K MRR. Liked team. |

---

## Advanced: Integrating DocSend Analytics

### Weekly Analytics Export (from DocSend)
1. Export visitor data from DocSend
2. Match emails to investor names
3. Update "Last View" and "Engagement Score" columns
4. Flag anyone who viewed but you haven't followed up with

### Automation Idea (Zapier/Make)
- Trigger: New DocSend view
- Action: Update Google Sheet row
- Result: Real-time tracking without manual updates

---

## Metrics to Track Weekly

### Pipeline Health
- **Total investors contacted**: _____
- **Response rate**: _____% (responded / contacted)
- **Meeting conversion**: _____% (meetings / responses)
- **Commit rate**: _____% (commits / meetings)

### Engagement Analysis
- **Avg DocSend view time**: _____ minutes
- **Avg pages viewed**: _____ / 12 pages
- **Most viewed slides**: _____ (check DocSend analytics)
- **Least viewed slides**: _____ (consider cutting these)

### Source Effectiveness
- **Warm intros → meetings**: _____%
- **Cold emails → meetings**: _____%
- **OpenVC → meetings**: _____%
- **Events → meetings**: _____%

---

## Red Flags to Watch For

⚠️ **Low Response Rate (<20%)**
- Issue: Outreach message needs work or targeting wrong investors
- Fix: A/B test email templates, refine investor list

⚠️ **High Meeting → Pass Rate (>80%)**
- Issue: Pitch needs refinement or not ready for market
- Fix: Practice pitch, get advisor feedback, build more traction

⚠️ **Low DocSend Engagement (<2 min avg)**
- Issue: Deck isn't compelling or too long
- Fix: Simplify deck, lead with strongest traction

⚠️ **Lots of Views, No Responses**
- Issue: CTA unclear or contact info missing
- Fix: Add explicit "Reply to schedule a call" on last slide

---

## Download Templates

### Google Sheets Template
Copy this template: [Create manually from the column structure above]

### Notion Template (Alternative)
If you prefer Notion:
1. Create database with same columns
2. Add views: "Active Pipeline", "Hot Leads", "Follow-ups"
3. Enable reminders for "Next Step" dates

### Airtable Template (Alternative)
Best for automation:
1. Import columns as fields
2. Set up filtered views
3. Connect to DocSend via Zapier for auto-updates

---

## Time Investment

- **Initial setup**: 30 minutes
- **Daily updates**: 5-10 minutes (morning and evening)
- **Weekly review**: 30 minutes (Friday afternoon)
- **Value**: Stay organized through 50+ investor conversations without dropping anyone

---

**Pro Tip**: Keep this open in a browser tab during your fundraise. Update immediately after every investor interaction while details are fresh.
