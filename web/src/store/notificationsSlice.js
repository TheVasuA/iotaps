import { createSlice, nanoid } from "@reduxjs/toolkit";

// Notifications slice (Task 19.7, Req 20.2). Holds the in-app notifications the
// SPA surfaces in the notification center. In-app notifications are delivered
// in real time over the per-session WebSocket as `{type:"notification", title,
// body}` frames (design "WebSocket message contract"; Notification_Sender
// persists the same rows server-side). This slice owns the client-side list,
// read state, and unread count for the bell/center UI.
//
// Newest notifications are kept at the head of the list; the list is capped so
// a long-lived session can't grow it without bound.

const MAX_NOTIFICATIONS = 100;

const initialState = {
  items: [], // [{ id, title, body, read, receivedAt }]
};

const notificationsSlice = createSlice({
  name: "notifications",
  initialState,
  reducers: {
    notificationReceived: {
      reducer(state, action) {
        state.items.unshift(action.payload);
        if (state.items.length > MAX_NOTIFICATIONS) {
          state.items.length = MAX_NOTIFICATIONS;
        }
      },
      prepare({ title, body, receivedAt } = {}) {
        return {
          payload: {
            id: nanoid(),
            title: title || null,
            body: body || null,
            read: false,
            receivedAt: receivedAt || new Date().toISOString(),
          },
        };
      },
    },
    markRead(state, action) {
      const item = state.items.find((n) => n.id === action.payload);
      if (item) item.read = true;
    },
    markAllRead(state) {
      for (const item of state.items) item.read = true;
    },
    clearNotifications(state) {
      state.items = [];
    },
  },
});

export const {
  notificationReceived,
  markRead,
  markAllRead,
  clearNotifications,
} = notificationsSlice.actions;
export default notificationsSlice.reducer;

// Selectors
export const selectNotifications = (s) => s.notifications.items;
export const selectUnreadCount = (s) =>
  s.notifications.items.reduce((n, item) => n + (item.read ? 0 : 1), 0);
