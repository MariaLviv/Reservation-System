import api from './api';

// Get admin phone from backend
export const getAdminPhone = async () => {
  const response = await api.get('/admin/phone');
  return response.data.phone;
};

// Admin Auth
export const sendAdminOTP = async (phone) => {
  const response = await api.post('/admin/send-otp', { phone });
  return response.data;
};

export const verifyAdminOTP = async (phone, code) => {
  const response = await api.post('/admin/verify-otp', { phone, code });
  if (response.data.session_token) {
    localStorage.setItem('adminToken', response.data.session_token);
  }
  return response.data;
};

export const adminLogout = () => {
  localStorage.removeItem('adminToken');
  return api.post('/admin/logout');
};

// Appointments Management
export const getAllAppointments = async (fromDate, toDate, status, search, skip = 0, limit = 10) => {
  const params = {
    skip,
    limit
  };
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;
  if (status) params.status = status;
  if (search) params.search = search;

  const response = await api.get('/admin/appointments', { params });
  return response.data;
};

export const updateAppointment = async (data) => {
  const response = await api.post('/admin/appointments/update', data);
  return response.data;
};

export const cancelAppointmentAdmin = async (appointmentId) => {
  const response = await api.post('/admin/appointments/cancel', null, {
    params: { appointment_id: appointmentId },
  });
  return response.data;
};

export const deleteAppointment = async (appointmentId) => {
  const response = await api.delete(`/admin/appointments/${appointmentId}`);
  return response.data;
};

// Schedule Management
export const updateSchedule = async (data) => {
  const response = await api.post('/admin/schedule', data);
  return response.data;
};

// Days Off
export const addDayOff = async (date) => {
  const response = await api.post('/admin/days-off', { date });
  return response.data;
};

export const removeDayOff = async (dayOffId) => {
  const response = await api.delete(`/admin/days-off/${dayOffId}`);
  return response.data;
};

// Blocked Slots
export const blockSlot = async (data) => {
  const response = await api.post('/admin/block-slot', data);
  return response.data;
};

export const unblockSlot = async (slotId) => {
  const response = await api.delete(`/admin/block-slot/${slotId}`);
  return response.data;
};

// User Management
export const getAllUsers = async (search, isBlacklisted, skip = 0, limit = 10) => {
  const params = {
    skip,
    limit
  };
  if (search) params.search = search;
  if (isBlacklisted !== undefined) params.is_blacklisted = isBlacklisted;

  const response = await api.get('/admin/users', { params });
  return response.data;
};

export const updateBlacklist = async (userId, isBlacklisted) => {
  const response = await api.post('/admin/users/blacklist', {
    user_id: userId,
    is_blacklisted: isBlacklisted,
  });
  return response.data;
};

export const addUserNote = async (userId, notes) => {
  const response = await api.post('/admin/users/note', {
    user_id: userId,
    notes,
  });
  return response.data;
};

// Reports
export const generateReport = async (fromDate, toDate) => {
  const response = await api.get('/admin/report', {
    params: {
      from_date: fromDate,
      to_date: toDate,
    },
  });
  return response.data;
};

// Dashboard Statistics
export const getDashboardStats = async () => {
  const response = await api.get('/admin/stats');
  return response.data;
};

// Export Reports
export const exportPDF = async (fromDate, toDate) => {
  const response = await api.get('/admin/export/pdf', {
    params: {
      from_date: fromDate,
      to_date: toDate,
    },
    responseType: 'blob'
  });
  return response.data;
};

export const exportExcel = async (fromDate, toDate) => {
  const response = await api.get('/admin/export/excel', {
    params: {
      from_date: fromDate,
      to_date: toDate,
    },
    responseType: 'blob'
  });
  return response.data;
};
