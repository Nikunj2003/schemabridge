/**
 * Who is signed in, and what they have left.
 *
 * Placeholder values until Google sign-in lands: the shell reads identity and
 * allowance from one place, so wiring it to the session means changing this
 * module rather than every screen.
 */
export const ACCOUNT = {
  name: "You",
  email: "signed-in@example.com",
};

export const USAGE = {
  runsUsed: 0,
  runsLimit: 10,
  callsUsed: 0,
  callsLimit: 30,
};
