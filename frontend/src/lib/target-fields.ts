/**
 * The target fields, as the UI needs them for table columns.
 *
 * Duplicated from the backend's schema deliberately: the tables need column
 * headers during the first render, before any request completes. `/api/schema`
 * remains the authority, and a mismatch shows up as a missing column rather
 * than as wrong data.
 */
import type { TargetField } from "./api";

export const TARGET_FIELDS: TargetField[] = [
  { name: "employeeId", label: "Employee ID", description: "", required: true, kind: "identifier", allowed_values: [] },
  { name: "fullName", label: "Full name", description: "", required: true, kind: "person_name", allowed_values: [] },
  { name: "workEmail", label: "Work email", description: "", required: true, kind: "email", allowed_values: [] },
  { name: "startDate", label: "Start date", description: "", required: true, kind: "date", allowed_values: [] },
  { name: "endDate", label: "End date", description: "", required: false, kind: "date", allowed_values: [] },
  { name: "department", label: "Department", description: "", required: false, kind: "text", allowed_values: [] },
  { name: "employmentType", label: "Employment type", description: "", required: false, kind: "enum", allowed_values: [] },
];
