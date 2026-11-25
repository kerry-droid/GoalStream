import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { api } from './api.js';
import { sessionReady, signedOut } from './store.js';
import Dashboard from './components/Dashboard.jsx';
import Landing from './components/Landing.jsx';
import MatchDetails from './components/MatchDetails.jsx';
import GoalPages from './components/GoalPages.jsx';

export default function App() {
  const dispatch = useDispatch();
  const status = useSelector(state => state.auth.status);

  useEffect(() => {
    api('/auth/refresh', { method: 'POST' }, false)
      .then(session => dispatch(sessionReady(session)))
      .catch(() => dispatch(signedOut()));
  }, [dispatch]);

  return <Routes>
    <Route path="/" element={<Dashboard />} />
    <Route path="/home" element={<Dashboard />} />
    <Route path="/live" element={<GoalPages page="live" />} />
    <Route path="/fixtures" element={<GoalPages page="fixtures" />} />
    <Route path="/competitions" element={<GoalPages page="competitions" />} />
    <Route path="/my-teams" element={<GoalPages page="teams" />} />
    <Route path="/match/demo-live" element={<Navigate to="/live" replace />} />
    <Route path="/match/demo-inter" element={<Navigate to="/live" replace />} />
    <Route path="/match/:matchId" element={<MatchDetails />} />
    <Route path="/account" element={status === 'authenticated' ? <Navigate to="/home" replace /> : <Landing />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
