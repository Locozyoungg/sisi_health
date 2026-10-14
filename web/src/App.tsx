import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Queue from "./pages/Queue";
import Vouchers from "./pages/Vouchers";

const queryClient = new QueryClient();

function RequireAuth({ children }: { children: React.ReactElement }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/queue" element={<RequireAuth><Queue /></RequireAuth>} />
          <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/vouchers" element={<RequireAuth><Vouchers /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/queue" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
