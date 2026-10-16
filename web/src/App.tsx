import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { getToken, setToken } from "./api";
import ConsultDetail from "./pages/ConsultDetail";
import CorridorQueue from "./pages/CorridorQueue";
import Dashboard from "./pages/Dashboard";
import EmployerDashboard from "./pages/EmployerDashboard";
import Facilities from "./pages/Facilities";
import FollowUpTracker from "./pages/FollowUpTracker";
import Login from "./pages/Login";
import Queue from "./pages/Queue";
import Referrals from "./pages/Referrals";
import SurgeryTracker from "./pages/SurgeryTracker";
import Vouchers from "./pages/Vouchers";

const queryClient = new QueryClient();

const NAV_LINKS = [
  { to: "/queue", label: "Queue" },
  { to: "/corridor", label: "Corridor" },
  { to: "/referrals", label: "Referrals" },
  { to: "/surgery", label: "Surgery" },
  { to: "/tracking", label: "Tracking" },
  { to: "/facilities", label: "Facilities" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/employer", label: "Employer" },
  { to: "/vouchers", label: "Vouchers" },
];

function RequireAuth({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />;
}

function NavBar() {
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <strong className="wordmark">SISI Health Console</strong>
        </span>
        <nav className="nav" aria-label="Console">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          className="btn btn-ghost btn-sm topbar-signout"
          onClick={() => {
            setToken(null);
            navigate("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

function AuthShell({ children }: { children: React.ReactElement }) {
  return (
    <RequireAuth>
      <div className="app-shell">
        <NavBar />
        {children}
      </div>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/queue" element={<AuthShell><Queue /></AuthShell>} />
          <Route path="/dashboard" element={<AuthShell><Dashboard /></AuthShell>} />
          <Route path="/employer" element={<AuthShell><EmployerDashboard /></AuthShell>} />
          <Route path="/vouchers" element={<AuthShell><Vouchers /></AuthShell>} />
          <Route path="/corridor" element={<AuthShell><CorridorQueue /></AuthShell>} />
          <Route path="/corridor/:id" element={<AuthShell><ConsultDetail /></AuthShell>} />
          <Route path="/referrals" element={<AuthShell><Referrals /></AuthShell>} />
          <Route path="/surgery" element={<AuthShell><SurgeryTracker /></AuthShell>} />
          <Route path="/tracking" element={<AuthShell><FollowUpTracker /></AuthShell>} />
          <Route path="/facilities" element={<AuthShell><Facilities /></AuthShell>} />
          <Route path="*" element={<Navigate to="/queue" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
