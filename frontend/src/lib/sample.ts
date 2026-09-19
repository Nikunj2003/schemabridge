/**
 * Sample data for the design preview.
 *
 * Taken from the real fixtures in `backend/fixtures/samples/`, so the screens
 * show the same employees, dates and failures the engine actually produces. The
 * preview is explicitly labelled and calls no services; it exists so the layout
 * and wording can be judged before anything is wired.
 */

export type StageId = "read" | "match" | "check" | "send" | "done";
export type StageState = "waiting" | "active" | "done" | "blocked";

export interface Stage {
  id: StageId;
  label: string;
  state: StageState;
  detail?: string;
}

export interface ActivityLine {
  id: string;
  at: string;
  text: string;
  detail?: string;
  tone: "neutral" | "ok" | "attention" | "problem";
}

export interface SourceValue {
  file: string;
  row: number;
  /** Shown as the client wrote it. */
  raw: string;
  /** The same value written so nobody has to guess the format. */
  reading?: string;
}

export interface Choice {
  id: string;
  label: string;
  consequence: string;
}

export interface Question {
  id: string;
  /** The business question, naming the employee where there is one. */
  title: string;
  subject: string;
  why: string;
  field: string;
  sources: SourceValue[];
  choices: Choice[];
  affected: number;
  /** Set once answered, so history reads back. */
  answer?: { label: string; at: string };
}

export interface RecordRow {
  employeeId: string;
  name: string;
  email: string;
  startDate: string;
  department: string;
  from: string[];
  state: "sent" | "failed" | "skipped" | "retrying" | "ready";
  destinationId?: string;
  note?: string;
}

/* ------------------------------------------------------------------ */
/* The run in progress: two exports, four real questions              */
/* ------------------------------------------------------------------ */

export const RUNNING_STAGES: Stage[] = [
  { id: "read", label: "Read files", state: "done", detail: "12 rows from 2 files" },
  { id: "match", label: "Match columns", state: "done", detail: "12 of 13 columns" },
  { id: "check", label: "Clean & check", state: "blocked", detail: "4 need your judgment" },
  { id: "send", label: "Send records", state: "waiting" },
  { id: "done", label: "Results", state: "waiting" },
];

export const IN_FLIGHT_STAGES: Stage[] = [
  { id: "read", label: "Read files", state: "done", detail: "12 rows from 2 files" },
  { id: "match", label: "Match columns", state: "active", detail: "Asking about 1 unfamiliar column" },
  { id: "check", label: "Clean & check", state: "waiting" },
  { id: "send", label: "Send records", state: "waiting" },
  { id: "done", label: "Results", state: "waiting" },
];

export const ACTIVITY: ActivityLine[] = [
  {
    id: "a1",
    at: "10:24:02",
    text: "Read 2 files",
    detail: "employees-legacy.csv and employees-hr-export.csv — 12 rows",
    tone: "neutral",
  },
  {
    id: "a2",
    at: "10:24:03",
    text: "Matched 12 columns",
    detail: "emp_id, emp_nm, doj and 9 others recognised from their names",
    tone: "ok",
  },
  {
    id: "a3",
    at: "10:24:09",
    text: "Asked about “Cost Centre Ref”",
    detail: "No target field matched. Left out — it has no home in the employee record",
    tone: "neutral",
  },
  {
    id: "a4",
    at: "10:24:10",
    text: "Combined 2 duplicate rows",
    detail: "Rahul Verma appears in both files and they agree",
    tone: "ok",
  },
  {
    id: "a5",
    at: "10:24:10",
    text: "Standardised 3 dates and trimmed 8 values",
    detail: "“14 March 2026” → 2026-03-14; extra spaces and casing tidied",
    tone: "ok",
  },
  {
    id: "a6",
    at: "10:24:11",
    text: "Stopped for 4 decisions",
    detail: "Each one changes what gets migrated, so it needs a person",
    tone: "attention",
  },
];

export const QUESTIONS: Question[] = [
  {
    id: "q-asha",
    title: "When did Asha Rao start?",
    subject: "Asha Rao · E-1003",
    why: "Both files have a start date for this employee, and they disagree by more than a year. Picking the wrong one would put the whole employment history out.",
    field: "Start date",
    sources: [
      { file: "employees-legacy.csv", row: 4, raw: "2 April 2026", reading: "2 April 2026" },
      { file: "employees-hr-export.csv", row: 3, raw: "2024-11-30", reading: "30 November 2024" },
    ],
    choices: [
      { id: "c1", label: "2 April 2026", consequence: "Use the legacy export's date." },
      { id: "c2", label: "30 November 2024", consequence: "Use the HR export's date." },
      { id: "c3", label: "Skip this employee", consequence: "Asha Rao will not be migrated. Recorded in the results." },
    ],
    affected: 1,
  },
  {
    id: "q-date-column",
    title: "What does the “Date” column mean?",
    subject: "employees-hr-export.csv · column 4",
    why: "The header only says “Date”. It could be the start date or the end date, and every row in this file depends on the answer.",
    field: "Unmapped column",
    sources: [{ file: "employees-hr-export.csv", row: 5, raw: "2026-08-31", reading: "31 August 2026" }],
    choices: [
      { id: "c1", label: "Start date", consequence: "When employment began." },
      { id: "c2", label: "End date", consequence: "When employment ended." },
      { id: "c3", label: "Leave this column out", consequence: "Nothing from it reaches the destination." },
    ],
    affected: 4,
  },
  {
    id: "q-vikram",
    title: "Which date is Vikram Nair's start date?",
    subject: "Vikram Nair · E-1004",
    why: "The file says 03/04/2026. That is 3 April in most of the world and 4 March in the United States, and nothing else in the file settles which.",
    field: "Start date",
    sources: [{ file: "employees-legacy.csv", row: 5, raw: "03/04/2026" }],
    choices: [
      { id: "c1", label: "3 April 2026", consequence: "Read as day first." },
      { id: "c2", label: "4 March 2026", consequence: "Read as month first." },
      { id: "c3", label: "Skip this employee", consequence: "Vikram Nair will not be migrated." },
    ],
    affected: 1,
  },
  {
    id: "q-meera",
    title: "Meera Joshi's email address is not usable",
    subject: "Meera Joshi · E-1005",
    why: "The address has two @ signs and a doubled dot. It cannot be tidied up safely, and the destination will reject it.",
    field: "Work email",
    sources: [{ file: "employees-legacy.csv", row: 6, raw: "meera.joshi@@example..com" }],
    choices: [
      { id: "c1", label: "Type the correct address", consequence: "Checked again before anything is sent." },
      { id: "c2", label: "Skip this employee", consequence: "Meera Joshi will not be migrated." },
    ],
    affected: 1,
  },
];

export const ANSWERED: Question[] = [
  {
    ...QUESTIONS[1],
    answer: { label: "Start date", at: "10:26" },
  },
];

/* ------------------------------------------------------------------ */
/* The finished run                                                    */
/* ------------------------------------------------------------------ */

export const DONE_STAGES: Stage[] = [
  { id: "read", label: "Read files", state: "done", detail: "12 rows" },
  { id: "match", label: "Match columns", state: "done", detail: "12 matched" },
  { id: "check", label: "Clean & check", state: "done", detail: "4 answered by you" },
  { id: "send", label: "Send records", state: "done", detail: "7 sent, 1 refused" },
  { id: "done", label: "Results", state: "done" },
];

export const RESULT_RECORDS: RecordRow[] = [
  {
    employeeId: "E-1001",
    name: "Priya Sharma",
    email: "Priya.Sharma@example.com",
    startDate: "2026-03-14",
    department: "Engineering",
    from: ["employees-legacy.csv row 2", "employees-directory.xlsx row 4"],
    state: "sent",
    destinationId: "DEST-9F2C10A4B7",
  },
  {
    employeeId: "E-1002",
    name: "Rahul Verma",
    email: "rahul.verma@example.com",
    startDate: "2026-01-06",
    department: "Finance",
    from: ["employees-legacy.csv row 3", "employees-hr-export.csv row 2"],
    state: "sent",
    destinationId: "DEST-41B8E0C3D9",
  },
  {
    employeeId: "E-1003",
    name: "Asha Rao",
    email: "asha.rao@example.com",
    startDate: "2026-04-02",
    department: "Operations",
    from: ["employees-legacy.csv row 4", "employees-hr-export.csv row 3"],
    state: "sent",
    destinationId: "DEST-7A15C2E880",
    note: "You chose 2 April 2026",
  },
  {
    employeeId: "000123",
    name: "Sanjay Gupta",
    email: "sanjay.gupta@example.com",
    startDate: "2026-05-11",
    department: "Finance",
    from: ["employees-legacy.csv row 7"],
    state: "sent",
    destinationId: "DEST-B03D9911EF",
    note: "Leading zeros kept",
  },
  {
    employeeId: "E-1007",
    name: "Deepa Iyer",
    email: "deepa.iyer@example.com",
    startDate: "2026-03-02",
    department: "Operations",
    from: ["employees-legacy.csv row 8"],
    state: "sent",
    destinationId: "DEST-5C7E2A0146",
    note: "Refused once as busy, accepted on the second try",
  },
  {
    employeeId: "E-2001",
    name: "Nisha Kapoor",
    email: "nisha.kapoor@example.com",
    startDate: "2026-06-01",
    department: "Marketing",
    from: ["employees-hr-export.csv row 4"],
    state: "sent",
    destinationId: "DEST-2E81B4FA07",
  },
  {
    employeeId: "E-2002",
    name: "Karan Singh",
    email: "karan.singh@example.com",
    startDate: "2026-06-15",
    department: "Marketing",
    from: ["employees-hr-export.csv row 5"],
    state: "sent",
    destinationId: "DEST-6D40A7C219",
  },
  {
    employeeId: "E-1008",
    name: "Arjun Mehta",
    email: "arjun.mehta@example.com",
    startDate: "2026-04-20",
    department: "Engineering",
    from: ["employees-legacy.csv row 9"],
    state: "failed",
    note: "Demo HR system refused this record: it fails a rule on their side, so it needs checking there before it can be sent again.",
  },
  {
    employeeId: "E-1004",
    name: "Vikram Nair",
    email: "vikram.nair@example.com",
    startDate: "—",
    department: "Engineering",
    from: ["employees-legacy.csv row 5"],
    state: "skipped",
    note: "You skipped this employee: the start date could not be settled",
  },
  {
    employeeId: "E-1005",
    name: "Meera Joshi",
    email: "meera.joshi@@example..com",
    startDate: "2026-02-17",
    department: "Design",
    from: ["employees-legacy.csv row 6"],
    state: "skipped",
    note: "You skipped this employee: the email address could not be corrected",
  },
];

export const RESULT_SUMMARY = {
  sourceRows: 12,
  employees: 10,
  merged: 2,
  sent: 7,
  failed: 1,
  skipped: 2,
  cleaned: 11,
  duration: "2 minutes 14 seconds",
};

/* ------------------------------------------------------------------ */
/* History and account                                                 */
/* ------------------------------------------------------------------ */

export interface HistoryRow {
  id: string;
  name: string;
  when: string;
  files: string[];
  state: "needs-you" | "running" | "done" | "done-with-problems";
  summary: string;
}

export const HISTORY: HistoryRow[] = [
  {
    id: "mig-4821",
    name: "September employee import",
    when: "Today at 10:24",
    files: ["employees-legacy.csv", "employees-hr-export.csv"],
    state: "needs-you",
    summary: "4 questions waiting",
  },
  {
    id: "mig-4806",
    name: "Contractor top-up",
    when: "Today at 09:02",
    files: ["employees-clean.csv"],
    state: "done",
    summary: "3 of 3 employees sent",
  },
  {
    id: "mig-4788",
    name: "Directory reconciliation",
    when: "Yesterday at 17:40",
    files: ["employees-directory.xlsx"],
    state: "done-with-problems",
    summary: "2 sent · 1 refused by the destination",
  },
];

export const USAGE = { runsUsed: 3, runsLimit: 10, aiUsed: 6, aiLimit: 30 };
export const ACCOUNT = { name: "Nikunj Khitha", email: "you@example.com" };
