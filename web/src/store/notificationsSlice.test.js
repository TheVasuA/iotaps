// Unit tests for the notifications slice (Task 19.7, Req 20.2). The reducer is
// pure, so it is exercised directly via the slice reducer + actions.

import { describe, it, expect } from "vitest";
import reducer, {
  notificationReceived,
  markRead,
  markAllRead,
  clearNotifications,
  selectUnreadCount,
} from "./notificationsSlice.js";

describe("notificationsSlice", () => {
  it("prepends a received notification with an id and unread state", () => {
    const state = reducer(
      undefined,
      notificationReceived({ title: "Alert", body: "Temp high" })
    );
    expect(state.items).toHaveLength(1);
    const n = state.items[0];
    expect(n.id).toBeTruthy();
    expect(n.title).toBe("Alert");
    expect(n.body).toBe("Temp high");
    expect(n.read).toBe(false);
    expect(n.receivedAt).toBeTruthy();
  });

  it("keeps the newest notification at the head", () => {
    let state = reducer(undefined, notificationReceived({ title: "first" }));
    state = reducer(state, notificationReceived({ title: "second" }));
    expect(state.items[0].title).toBe("second");
    expect(state.items[1].title).toBe("first");
  });

  it("caps the list at 100 entries", () => {
    let state;
    for (let i = 0; i < 105; i += 1) {
      state = reducer(state, notificationReceived({ title: `n${i}` }));
    }
    expect(state.items).toHaveLength(100);
    // newest kept, oldest dropped
    expect(state.items[0].title).toBe("n104");
  });

  it("marks a single notification read by id", () => {
    let state = reducer(undefined, notificationReceived({ title: "a" }));
    const id = state.items[0].id;
    state = reducer(state, markRead(id));
    expect(state.items[0].read).toBe(true);
  });

  it("marks all notifications read", () => {
    let state = reducer(undefined, notificationReceived({ title: "a" }));
    state = reducer(state, notificationReceived({ title: "b" }));
    state = reducer(state, markAllRead());
    expect(state.items.every((n) => n.read)).toBe(true);
  });

  it("clears all notifications", () => {
    let state = reducer(undefined, notificationReceived({ title: "a" }));
    state = reducer(state, clearNotifications());
    expect(state.items).toHaveLength(0);
  });

  it("selectUnreadCount counts only unread items", () => {
    let state = reducer(undefined, notificationReceived({ title: "a" }));
    state = reducer(state, notificationReceived({ title: "b" }));
    expect(selectUnreadCount({ notifications: state })).toBe(2);
    state = reducer(state, markRead(state.items[0].id));
    expect(selectUnreadCount({ notifications: state })).toBe(1);
  });
});
