import api from './api';

// OTP Services
export const sendOTP = async (phone) => {
  const response = await api.post('/auth/send-otp', { phone });
  return response.data;
};

export const verifyOTP = async (phone, code) => {
  const response = await api.post('/auth/verify-otp', { phone, code });
  return response.data;
};

// Slots Services with in-memory cache
const slotsCache = new Map();
const inFlightRequests = new Map();
const CACHE_TTL = 60000; // 1 minute cache

export const getAvailableSlots = async (fromDate, toDate) => {
  const cacheKey = `${fromDate}_${toDate}`;

  // Check cache first
  const cached = slotsCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }

  // Check if request is already in flight
  const inFlight = inFlightRequests.get(cacheKey);
  if (inFlight) {
    return inFlight;
  }

  // Make new request
  const requestPromise = api.get('/slots', {
    params: {
      from_date: fromDate,
      to_date: toDate,
    },
  }).then(response => {
    // Cache the result
    slotsCache.set(cacheKey, {
      data: response.data,
      timestamp: Date.now()
    });
    // Clear in-flight marker
    inFlightRequests.delete(cacheKey);
    return response.data;
  }).catch(error => {
    // Clear in-flight marker on error
    inFlightRequests.delete(cacheKey);
    throw error;
  });

  // Store in-flight request
  inFlightRequests.set(cacheKey, requestPromise);

  return requestPromise;
};

// Clear slots cache (useful after booking/cancellation)
export const clearSlotsCache = () => {
  slotsCache.clear();
  inFlightRequests.clear();
};

// Appointments Services
export const createAppointment = async (data) => {
  const response = await api.post('/appointments', data);
  return response.data;
};

export const cancelAppointment = async (appointmentId, phone) => {
  const response = await api.delete(`/appointments/${appointmentId}`, {
    params: { phone },
  });
  return response.data;
};

export const deleteAppointment = async (appointmentId, phone) => {
  const response = await api.delete(`/appointments/${appointmentId}/delete`, {
    params: { phone },
  });
  return response.data;
};

export const getUserAppointments = async (phone) => {
  const response = await api.get('/appointments', {
    params: { phone },
  });
  return response.data;
};

// Profile Services
export const getUserProfile = async (phone) => {
  const response = await api.get('/profile', {
    params: { phone },
  });
  return response.data;
};

export const createOrUpdateProfile = async (phone, name, birthdate) => {
  const response = await api.post('/profile', null, {
    params: { phone, name, birthdate },
  });
  return response.data;
};

// Days Off Service
export const getDaysOff = async () => {
  const response = await api.get('/days-off');
  return response.data;
};
