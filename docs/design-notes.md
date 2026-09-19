# Design notes

## Who this is for

An implementation consultant, mid-migration, with a client waiting. They
understand the client's business data. They do not read schemas, and they will
not debug a mapping. Their job is to answer the questions only a person can
answer, and to be able to say afterwards what happened to every record.

That audience rules out two tempting directions. It is not a developer console —
no JSON, no confidence scores, no "0.87". And it is not a wizard — a
step-by-step flow implies every field needs confirming, which is exactly the
micromanagement this is meant to avoid.

## The design thesis

**The screen's job is to make the agent's work legible, and the human's work
small.**

Most of the interface is a record of decisions already made. The part that needs
attention is one queue, and it should be obvious at a glance how many items are
in it and what each one is asking.

A consequence worth stating: when the agent has nothing to ask, the review area
is empty and that is the success state, not an unfinished one.

## Layout

A workbench, not a dashboard. Dashboards are for monitoring; this is for doing.

```
┌────────────────────────────────────────────────────────────────┐
│ SchemaBridge          employees-legacy.csv +2    ● Working      │  56px
├──────────────────────┬─────────────────────────────────────────┤
│                      │                                         │
│  NEEDS YOU      2    │   "Date" could be Start date            │
│  ┌────────────────┐  │   or End date                           │
│  │ Date → ?       │← │                                         │
│  │ hr-export.csv  │  │   employees-hr-export.csv, column 4     │
│  └────────────────┘  │   Values look like: 2026-08-31           │
│  ┌────────────────┐  │                                         │
│  │ E-1003 conflict│  │   Both readings are valid dates, so      │
│  └────────────────┘  │   choosing wrong would silently          │
│                      │   misdate every record in this file.     │
│  ACTIVITY            │                                         │
│  ✓ emp_id mapped     │   ┌──────────────┐ ┌──────────────┐     │
│  ✓ doj → 2026-03-14  │   │ Start date   │ │ End date     │     │
│  ✓ E-1002 merged     │   └──────────────┘ └──────────────┘     │
│  ⋯ asking the model  │   ┌──────────────────────────────┐     │
│                      │   │ Leave this column out        │     │
│                      │   └──────────────────────────────┘     │
├──────────────────────┴─────────────────────────────────────────┤
│  12 mapped · 10 records · 2 merged · 6 delivered · 1 retrying   │
└────────────────────────────────────────────────────────────────┘
```

Left rail: what needs a person, and what the agent has been doing. Right: the
one decision in focus, with everything needed to make it.

The tabs across the workspace — Review, Records, Delivery, Audit — because
"see a clear record of everything it did" is a separate job from resolving a
queue, and mixing them makes both worse.

## Three actions, no more

The brief names approve, correct, reject. The interface offers exactly those,
phrased as what they do rather than what they are:

- The recommended option is a button with the target's name on it. Approving is
  choosing it.
- Correcting is choosing a different option, or typing a value.
- Rejecting is "Leave this out", which always states its consequence.

No confirmation dialogs. Every action is visible in the audit trail and the run
can be re-run, so a modal asking "are you sure" would only add friction to the
one task the person is here to do.

## What replaces a confidence score

Never a percentage. A consultant cannot act on 0.87.

Instead, the reason the agent stopped, in its own words:

> Both readings are valid dates, so choosing wrong would silently misdate every
> record in this file.

The evidence is already in the domain layer — every escalation carries a
plain-language `reason`. The UI's job is to show it prominently rather than
bury it under a score.

## Live without fake progress

The activity feed is committed audit events, polled. Each line is something that
actually happened, with its reason. No spinner standing in for work, no
percentage bar counting to an invented total.

When the run is waiting on a person, the feed says so and stops — a feed that
keeps animating while nothing happens teaches people to ignore it.
