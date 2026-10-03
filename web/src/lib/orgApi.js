import apiClient from "@/lib/apiClient";

export async function getOrgProfile() {
  const { data } = await apiClient.get("/org/profile");
  return data;
}

export async function listOrgMembers() {
  const { data } = await apiClient.get("/org/members");
  return data;
}

export async function createOrgMember({ email, password, role = "device_user" }) {
  const { data } = await apiClient.post("/org/members", { email, password, role });
  return data;
}

export async function upgradeToCompany({ organizationName }) {
  const { data } = await apiClient.post("/org/upgrade-to-company", {
    organization_name: organizationName,
  });
  return data;
}
