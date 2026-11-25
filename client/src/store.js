import { configureStore, createSlice } from '@reduxjs/toolkit';

const readFootballState = () => {
  try { return { teams: JSON.parse(localStorage.getItem('goalstream:teams') || '[]'), reminders: JSON.parse(localStorage.getItem('goalstream:reminders') || '[]') }; }
  catch { return { teams: [], reminders: [] }; }
};

const authSlice = createSlice({ name: 'auth', initialState: { user: null, accessToken: null, status: 'checking' }, reducers: {
  sessionReady(state, action) { state.user = action.payload.user; state.accessToken = action.payload.accessToken; state.status = 'authenticated'; },
  signedOut(state) { state.user = null; state.accessToken = null; state.status = 'anonymous'; }
} });
export const { sessionReady, signedOut } = authSlice.actions;

const footballSlice = createSlice({ name: 'football', initialState: readFootballState(), reducers: {
  teamFollowed(state, action) { if (!state.teams.some(team => team.name === action.payload.name)) state.teams.push(action.payload); },
  teamUnfollowed(state, action) { state.teams = state.teams.filter(team => team.name !== action.payload); },
  reminderToggled(state, action) { state.reminders = state.reminders.includes(action.payload) ? state.reminders.filter(id => id !== action.payload) : [...state.reminders, action.payload]; },
} });
export const { teamFollowed, teamUnfollowed, reminderToggled } = footballSlice.actions;
export const store = configureStore({ reducer: { auth: authSlice.reducer, football: footballSlice.reducer } });
if (typeof window !== 'undefined') store.subscribe(() => {
  try {
    const { teams, reminders } = store.getState().football;
    localStorage.setItem('goalstream:teams', JSON.stringify(teams));
    localStorage.setItem('goalstream:reminders', JSON.stringify(reminders));
  } catch { /* Storage may be disabled; the Redux state still works for this session. */ }
});
