import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import {
  listRules,
  getRule,
  createRule,
  updateRule,
  deleteRule,
  createRuleFromTemplate,
  listTemplates,
} from "@/lib/rulesApi";
import { extractApiError } from "@/lib/authApi";

// Rules slice (Task 10.5, Req 10.1, 10.5): owns the rule list, the active rule
// being edited (with its React Flow graph), the template catalog (for
// instantiation), and request status for the visual rule editor. Async thunks
// wrap the rulesApi calls; reducers keep the cached list in sync so the editor
// and list views update without an extra round trip.

const initialState = {
  items: [], // [rule] {id, org_id, name, enabled, template_id}
  current: null, // { rule, nodes, edges } of the active rule
  templates: [], // [template] for the "from template" picker
  status: "idle", // idle | loading | succeeded | failed
  saving: false,
  error: null,
};

export const fetchRules = createAsyncThunk(
  "rules/fetchAll",
  async (_, { rejectWithValue }) => {
    try {
      return await listRules();
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const fetchRule = createAsyncThunk(
  "rules/fetchOne",
  async (id, { rejectWithValue }) => {
    try {
      return await getRule(id);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const createNewRule = createAsyncThunk(
  "rules/create",
  async (payload, { rejectWithValue }) => {
    try {
      return await createRule(payload);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const saveRule = createAsyncThunk(
  "rules/save",
  async ({ id, changes }, { rejectWithValue }) => {
    try {
      return await updateRule(id, changes);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const removeRule = createAsyncThunk(
  "rules/remove",
  async (id, { rejectWithValue }) => {
    try {
      await deleteRule(id);
      return id;
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const instantiateTemplate = createAsyncThunk(
  "rules/fromTemplate",
  async (templateId, { rejectWithValue }) => {
    try {
      return await createRuleFromTemplate(templateId);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const fetchTemplates = createAsyncThunk(
  "rules/fetchTemplates",
  async (category, { rejectWithValue }) => {
    try {
      return await listTemplates(category);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

const rulesSlice = createSlice({
  name: "rules",
  initialState,
  reducers: {
    clearCurrentRule(state) {
      state.current = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchRules.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchRules.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchRules.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload?.message || "Failed to load rules";
      })
      .addCase(fetchRule.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchRule.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.current = action.payload;
      })
      .addCase(fetchRule.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload?.message || "Failed to load rule";
      })
      .addCase(createNewRule.pending, (state) => {
        state.saving = true;
        state.error = null;
      })
      .addCase(createNewRule.fulfilled, (state, action) => {
        state.saving = false;
        state.items.unshift(action.payload);
      })
      .addCase(createNewRule.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload?.message || "Failed to create rule";
      })
      .addCase(saveRule.pending, (state) => {
        state.saving = true;
        state.error = null;
      })
      .addCase(saveRule.fulfilled, (state, action) => {
        state.saving = false;
        const idx = state.items.findIndex((r) => r.id === action.payload.id);
        if (idx >= 0) state.items[idx] = action.payload;
        if (state.current?.rule?.id === action.payload.id) {
          state.current.rule = action.payload;
        }
      })
      .addCase(saveRule.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload?.message || "Failed to save rule";
      })
      .addCase(removeRule.fulfilled, (state, action) => {
        state.items = state.items.filter((r) => r.id !== action.payload);
        if (state.current?.rule?.id === action.payload) state.current = null;
      })
      .addCase(instantiateTemplate.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
      })
      .addCase(fetchTemplates.fulfilled, (state, action) => {
        state.templates = action.payload;
      });
  },
});

export const { clearCurrentRule } = rulesSlice.actions;
export default rulesSlice.reducer;

// Selectors
export const selectRules = (s) => s.rules.items;
export const selectCurrentRule = (s) => s.rules.current;
export const selectRuleTemplates = (s) => s.rules.templates;
export const selectRulesStatus = (s) => s.rules.status;
export const selectRulesSaving = (s) => s.rules.saving;
export const selectRulesError = (s) => s.rules.error;
export const selectRuleById = (id) => (s) =>
  s.rules.items.find((r) => r.id === id) || null;
