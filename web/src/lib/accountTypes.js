export const ACCOUNT_INDIVIDUAL = "individual";
export const ACCOUNT_STUDENT = "student";
export const ACCOUNT_COMPANY = "company";

export const SIGNUP_ACCOUNT_OPTIONS = [
  { id: ACCOUNT_INDIVIDUAL, title: "Individual", subtitle: "Customer" },
  { id: ACCOUNT_STUDENT, title: "Student", subtitle: "Learning" },
  { id: ACCOUNT_COMPANY, title: "Company", subtitle: "Organization" },
];

export function isCompanyAccount(user) {
  return user?.account_type === ACCOUNT_COMPANY;
}

export function canManageOrgUsers(user) {
  return isCompanyAccount(user) && user?.role === "project_center";
}

export const SIGNUP_STORAGE_KEY = "iotaps.signup.account_type";
export const SIGNUP_ORG_NAME_KEY = "iotaps.signup.organization_name";
