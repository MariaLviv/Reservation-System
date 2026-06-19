import React, { useState, useEffect, useCallback } from 'react';
import { format, parseISO } from 'date-fns';
import { uk } from 'date-fns/locale';
import { toast } from 'react-toastify';
import { getAvailableSlots, createAppointment, getUserAppointments, cancelAppointment, deleteAppointment, sendOTP, verifyOTP, getUserProfile, createOrUpdateProfile, clearSlotsCache, getDaysOff } from '../services/userService';
import { getUserPhone, saveUserSession } from '../utils/storage';
import { addMonths, isBefore, isWeekend, startOfDay, addDays, isSameDay } from 'date-fns';
import Calendar from 'react-calendar';
import 'react-calendar/dist/Calendar.css';
import '../styles/BookingPageSimple.css';
import '../styles/SlotPicker.css'; /* For calendar dark theme */

const BookingPage = ({ onUserVerified }) => {
  // Auth state
  const [phone, setPhone] = useState(() => getUserPhone() || '');
  const [verified, setVerified] = useState(() => !!getUserPhone());
  const [otpCode, setOtpCode] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpLoading, setOtpLoading] = useState(false);
  const [showProfileForm, setShowProfileForm] = useState(false);
  const [profileFirstName, setProfileFirstName] = useState('');
  const [profileLastName, setProfileLastName] = useState('');
  const [profileBirthdate, setProfileBirthdate] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);

  // Booking state
  const [step, setStep] = useState(1); // 1: date, 2: time
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsLoaded, setSlotsLoaded] = useState(false); // Track if slots were loaded for current date
  const [daysOff, setDaysOff] = useState([]);
  const [userAppointments, setUserAppointments] = useState([]);
  const [appointmentsLoading, setAppointmentsLoading] = useState(false);
  const [initialLoadDone, setInitialLoadDone] = useState(false); // Prevent multiple initial loads

  const maxDate = addMonths(new Date(), 6);

  const loadDaysOff = useCallback(async () => {
    try {
      const data = await getDaysOff();
      const dates = data.map(d => parseISO(d.date));
      setDaysOff(dates);
    } catch (error) {
      console.error('Error fetching days off:', error);
    }
  }, []);

  const loadUserAppointments = useCallback(async () => {
    setAppointmentsLoading(true);
    try {
      const data = await getUserAppointments(phone);
      setUserAppointments(data || []);
    } catch (error) {
      console.error('Error fetching appointments:', error);
    } finally {
      setAppointmentsLoading(false);
    }
  }, [phone]);

  const loadSlots = useCallback(async () => {
    if (!selectedDate || slotsLoading) return;
    setSlotsLoading(true);
    try {
      const dateStr = format(selectedDate, 'yyyy-MM-dd');
      const data = await getAvailableSlots(dateStr, dateStr);
      setSlots(data);
      setSlotsLoaded(true);
    } catch (error) {
      toast.error('Помилка завантаження слотів');
      setSlotsLoaded(true); // Mark as loaded even on error to prevent infinite retries
    } finally {
      setSlotsLoading(false);
    }
  }, [selectedDate, slotsLoading]);

  const isDayOff = useCallback((date) => {
    return daysOff.some(dayOff => isSameDay(startOfDay(dayOff), startOfDay(date)));
  }, [daysOff]);

  const findFirstAvailableDate = useCallback(async () => {
    let checkDate = new Date();
    const maxCheckDate = addDays(new Date(), 30);

    while (isBefore(checkDate, maxCheckDate)) {
      // Skip weekends - don't need daysOff check here for initial load
      if (!isWeekend(checkDate)) {
        try {
          const dateStr = format(checkDate, 'yyyy-MM-dd');
          const data = await getAvailableSlots(dateStr, dateStr);
          if (data && data.length > 0) {
            setSelectedDate(checkDate);
            // Store the slots we just fetched to avoid refetching
            setSlots(data);
            setSlotsLoaded(true);
            setSlotsLoading(false);
            return;
          }
        } catch (error) {
          console.error('Error checking date:', error);
        }
      }
      checkDate = addDays(checkDate, 1);
    }
    setSelectedDate(new Date());
    setSlotsLoaded(true);
  }, []); // No dependencies - runs once

  // Auto-find first available date and load days-off (runs once when verified)
  useEffect(() => {
    if (verified && !initialLoadDone) {
      setInitialLoadDone(true);
      loadDaysOff();
      loadUserAppointments();
      findFirstAvailableDate();
    }
  }, [verified, initialLoadDone, loadDaysOff, loadUserAppointments, findFirstAvailableDate]);

  // Load slots when date changes manually (not from findFirstAvailableDate)
  useEffect(() => {
    if (selectedDate && !slotsLoaded && !slotsLoading) {
      loadSlots();
    }
  }, [selectedDate, slotsLoaded, slotsLoading, loadSlots]);

  const handleCancelAppointment = async (appointmentId) => {
    if (!window.confirm('Скасувати цей запис?')) return;

    try {
      await cancelAppointment(appointmentId, phone);
      toast.success('Запис скасовано');

      // Clear cache so slots are refreshed
      clearSlotsCache();

      // Reload appointments list (user-cancelled ones will be filtered out by backend)
      loadUserAppointments();

      // Reload slots to show the freed time
      if (selectedDate) {
        setSlots([]); // Clear current slots
        setSlotsLoaded(false); // Trigger reload
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка скасування');
    }
  };

  const handleDeleteAppointment = async (appointmentId) => {
    if (!window.confirm('Видалити цей запис зі списку?')) return;

    try {
      await deleteAppointment(appointmentId, phone);
      toast.success('Запис видалено');

      // Reload appointments list
      loadUserAppointments();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка видалення');
    }
  };

  const handleSendOTP = async () => {
    if (!phone || phone.length < 10) {
      toast.error('Введіть коректний номер телефону');
      return;
    }

    setOtpLoading(true);
    try {
      await sendOTP(phone);
      setOtpSent(true);
      toast.success('Код відправлено на ваш телефон');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка відправки коду');
    } finally {
      setOtpLoading(false);
    }
  };

  const handleVerifyOTP = async () => {
    if (!otpCode || otpCode.length !== 6) {
      toast.error('Введіть 6-значний код');
      return;
    }

    setOtpLoading(true);
    try {
      await verifyOTP(phone, otpCode);

      // Check if user profile exists
      try {
        await getUserProfile(phone);
        // Profile exists, user is complete
        setVerified(true);
        saveUserSession(phone);
        toast.success('Вхід виконано');
        if (onUserVerified) {
          onUserVerified(phone);
        }
      } catch (error) {
        if (error.response?.status === 404) {
          // Profile doesn't exist, show profile form
          setShowProfileForm(true);
          toast.info('Заповніть ваші дані');
        } else {
          throw error;
        }
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Невірний код');
    } finally {
      setOtpLoading(false);
    }
  };

  const handleProfileSubmit = async (e) => {
    e.preventDefault();

    if (!profileFirstName || !profileLastName || !profileBirthdate) {
      toast.error('Заповніть всі поля');
      return;
    }

    // Combine first and last name
    const fullName = `${profileLastName.trim()} ${profileFirstName.trim()}`;

    setProfileLoading(true);
    try {
      await createOrUpdateProfile(phone, fullName, profileBirthdate);
      setVerified(true);
      saveUserSession(phone);
      toast.success('Профіль створено');
      if (onUserVerified) {
        onUserVerified(phone);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка збереження профілю');
    } finally {
      setProfileLoading(false);
    }
  };

  const tileDisabled = ({ date }) => {
    if (isDayOff(date)) return true;
    if (isWeekend(date)) return true;
    if (isBefore(maxDate, startOfDay(date))) return true;
    if (isBefore(date, startOfDay(new Date()))) return true;
    return false;
  };

  const tileClassName = ({ date, view }) => {
    if (view === 'month' && isDayOff(date)) {
      return 'day-off-tile';
    }
    return null;
  };

  const handleSlotSelect = async (slot) => {
    // Immediately book the slot using profile data from database
    setSelectedSlot(slot);

    try {
      // Get user profile from database
      const profile = await getUserProfile(phone);

      // Create appointment immediately
      await createAppointment({
        phone,
        name: profile.name,
        birthdate: profile.birthdate,
        start_time: slot.start_time,
        end_time: slot.end_time
      });

      toast.success('✅ Запис успішно створено!');

      // Clear cache so slots are refreshed
      clearSlotsCache();

      // Reset to calendar view (step 1)
      setStep(1);
      setSelectedDate(null);
      setSelectedSlot(null);
      setSlots([]); // Clear slots
      setSlotsLoaded(false);
      setInitialLoadDone(false); // Allow re-finding first available date

      // Reload appointments
      loadUserAppointments();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка створення запису');
      setSelectedSlot(null);
    }
  };

  return (
    <div className="booking-page-simple">
      {!verified ? (
        // Phone verification or profile setup
        <div className="auth-container">
          <div className="auth-card">
            {!showProfileForm ? (
              <>
                <h1>📱 Підтвердження телефону</h1>
                <p>Введіть ваш номер телефону для запису на прийом</p>

                {!otpSent ? (
                  <div className="phone-input-section">
                    <input
                      type="tel"
                      placeholder="+380501234567"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value.replace(/\s/g, ''))}
                      className="phone-input"
                    />
                    <button
                      onClick={handleSendOTP}
                      disabled={otpLoading}
                      className="btn-primary-large"
                    >
                      {otpLoading ? 'Відправка...' : 'Отримати код'}
                    </button>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: '0.5rem' }}>
                      Тестовий доступ: +380999999999 (будь-який код)
                    </p>
                  </div>
                ) : (
                  <div className="otp-input-section">
                    <p className="otp-hint">Введіть код з SMS</p>
                    <input
                      type="text"
                      placeholder="123456"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value.replace(/\s/g, ''))}
                      onPaste={(e) => {
                        e.preventDefault();
                        const pastedText = e.clipboardData.getData('text').replace(/\s/g, '');
                        setOtpCode(pastedText.slice(0, 6));
                      }}
                      maxLength="6"
                      className="otp-input"
                    />
                    <p className="telegram-hint">
                      💬 Або отримайте код через{' '}
                      <a
                        href="https://t.me/Toka_12_bot"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="telegram-link"
                      >
                        Telegram Bot @Toka_12_bot
                      </a>
                    </p>
                    <button
                      onClick={handleVerifyOTP}
                      disabled={otpLoading}
                      className="btn-primary-large"
                    >
                      {otpLoading ? 'Перевірка...' : 'Підтвердити'}
                    </button>
                    <button
                      onClick={() => setOtpSent(false)}
                      className="btn-text"
                    >
                      Змінити номер
                    </button>
                  </div>
                )}
              </>
            ) : (
              <>
                <h1>👤 Ваші дані</h1>
                <p>Заповніть інформацію для запису</p>

                <form onSubmit={handleProfileSubmit} className="phone-input-section">
                  <input
                    type="text"
                    placeholder="Прізвище"
                    value={profileLastName}
                    onChange={(e) => setProfileLastName(e.target.value)}
                    className="phone-input"
                    required
                  />
                  <input
                    type="text"
                    placeholder="Ім'я"
                    value={profileFirstName}
                    onChange={(e) => setProfileFirstName(e.target.value)}
                    className="phone-input"
                    required
                  />
                  <div className="birthdate-input-wrapper">
                    <span className="birthdate-calendar-icon" aria-hidden="true">📅</span>
                    <input
                      type="date"
                      placeholder="Дата народження"
                      value={profileBirthdate}
                      onChange={(e) => setProfileBirthdate(e.target.value)}
                      className="phone-input birthdate-input"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={profileLoading}
                    className="btn-primary-large"
                  >
                    {profileLoading ? 'Збереження...' : 'Продовжити'}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      ) : (
        // Booking flow
        <div className="booking-container">
          {step === 1 && selectedDate && (
            <div className="calendar-step">
              <div className="calendar-with-appointments">
                {/* Left side: User appointments */}
                <div className="user-appointments-sidebar">
                  <h3>📋 Мої записи</h3>
                  {appointmentsLoading ? (
                    <div className="loading">Завантаження...</div>
                  ) : userAppointments.length === 0 ? (
                    <div className="no-appointments-state">
                      <div className="empty-icon">📅</div>
                      <p className="empty-title">Немає активних записів</p>
                      <p className="empty-subtitle">Оберіть дату та час для запису на прийом</p>
                    </div>
                  ) : (
                    <div className="appointments-list">
                      {(() => {
                        const now = new Date();
                        const today = startOfDay(now);
                        const tomorrow = addDays(today, 1);

                        const todayApts = userAppointments.filter(apt =>
                          isSameDay(new Date(apt.start_time), today)
                        );
                        const tomorrowApts = userAppointments.filter(apt =>
                          isSameDay(new Date(apt.start_time), tomorrow)
                        );
                        const laterApts = userAppointments.filter(apt => {
                          const aptDate = new Date(apt.start_time);
                          return aptDate > tomorrow && !isSameDay(aptDate, tomorrow);
                        });

                        return (
                          <>
                            {todayApts.length > 0 && (
                              <div className="apt-group">
                                <div className="apt-group-title">Сьогодні</div>
                                {todayApts.map((apt) => (
                                  <div key={apt.id} className="appointment-card">
                                    <div className="apt-icon">🩺</div>
                                    <div className="apt-content">
                                      <div className="apt-header">
                                        <div className="apt-date">
                                          {format(new Date(apt.start_time), 'EEEE, d MMMM', { locale: uk })}
                                        </div>
                                        <span className={`apt-badge ${apt.status === 'booked' ? 'badge-today' : 'badge-cancelled'}`}>
                                          {apt.status === 'booked' ? 'Сьогодні' : 'Скасовано'}
                                        </span>
                                      </div>
                                      <div className="apt-time">
                                        ⏰ {format(new Date(apt.start_time), 'HH:mm')}
                                      </div>
                                      <div className="apt-name">👤 {apt.user?.name || 'Пацієнт'}</div>
                                    </div>
                                    {apt.status === 'booked' && (
                                      <button
                                        onClick={() => handleCancelAppointment(apt.id)}
                                        className="btn-cancel-apt"
                                        title="Скасувати запис"
                                      >
                                        ✕
                                      </button>
                                    )}
                                    {apt.status === 'cancelled' && (
                                      <button
                                        onClick={() => handleDeleteAppointment(apt.id)}
                                        className="btn-delete-apt"
                                        title="Видалити зі списку"
                                      >
                                        🗑️
                                      </button>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}

                            {tomorrowApts.length > 0 && (
                              <div className="apt-group">
                                <div className="apt-group-title">Завтра</div>
                                {tomorrowApts.map((apt) => (
                                  <div key={apt.id} className="appointment-card">
                                    <div className="apt-icon">🩺</div>
                                    <div className="apt-content">
                                      <div className="apt-header">
                                        <div className="apt-date">
                                          {format(new Date(apt.start_time), 'EEEE, d MMMM', { locale: uk })}
                                        </div>
                                        <span className={`apt-badge ${apt.status === 'booked' ? 'badge-tomorrow' : 'badge-cancelled'}`}>
                                          {apt.status === 'booked' ? 'Завтра' : 'Скасовано'}
                                        </span>
                                      </div>
                                      <div className="apt-time">
                                        ⏰ {format(new Date(apt.start_time), 'HH:mm')}
                                      </div>
                                      <div className="apt-name">👤 {apt.user?.name || 'Пацієнт'}</div>
                                    </div>
                                    {apt.status === 'booked' && (
                                      <button
                                        onClick={() => handleCancelAppointment(apt.id)}
                                        className="btn-cancel-apt"
                                        title="Скасувати запис"
                                      >
                                        ✕
                                      </button>
                                    )}
                                    {apt.status === 'cancelled' && (
                                      <button
                                        onClick={() => handleDeleteAppointment(apt.id)}
                                        className="btn-delete-apt"
                                        title="Видалити зі списку"
                                      >
                                        🗑️
                                      </button>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}

                            {laterApts.length > 0 && (
                              <div className="apt-group">
                                <div className="apt-group-title">Пізніше</div>
                                {laterApts.map((apt) => (
                                  <div key={apt.id} className="appointment-card">
                                    <div className="apt-icon">🩺</div>
                                    <div className="apt-content">
                                      <div className="apt-header">
                                        <div className="apt-date">
                                          {format(new Date(apt.start_time), 'EEEE, d MMMM', { locale: uk })}
                                        </div>
                                        <span className={`apt-badge ${apt.status === 'booked' ? 'badge-upcoming' : 'badge-cancelled'}`}>
                                          {apt.status === 'booked' ? 'Заплановано' : 'Скасовано'}
                                        </span>
                                      </div>
                                      <div className="apt-time">
                                        ⏰ {format(new Date(apt.start_time), 'HH:mm')}
                                      </div>
                                      <div className="apt-name">👤 {apt.user?.name || 'Пацієнт'}</div>
                                    </div>
                                    {apt.status === 'booked' && (
                                      <button
                                        onClick={() => handleCancelAppointment(apt.id)}
                                        className="btn-cancel-apt"
                                        title="Скасувати запис"
                                      >
                                        ✕
                                      </button>
                                    )}
                                    {apt.status === 'cancelled' && (
                                      <button
                                        onClick={() => handleDeleteAppointment(apt.id)}
                                        className="btn-delete-apt"
                                        title="Видалити зі списку"
                                      >
                                        🗑️
                                      </button>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  )}
                </div>

                {/* Right side: Calendar */}
                <div className="calendar-section">
                  <h2>Оберіть дату</h2>
                  <Calendar
                    onChange={(date) => {
                      setSelectedDate(date);
                      setSlots([]); // Clear slots to trigger fresh load for manually selected date
                      setSlotsLoaded(false); // Reset loaded flag
                      setStep(2);
                    }}
                    value={selectedDate}
                    tileDisabled={tileDisabled}
                    tileClassName={tileClassName}
                    locale="uk-UA"
                    minDate={new Date()}
                    maxDate={maxDate}
                  />
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="time-step">
              <button onClick={() => setStep(1)} className="btn-back">
                ← Назад до календаря
              </button>
              <h2>Оберіть час на {format(selectedDate, 'dd MMMM yyyy', { locale: uk })}</h2>

              {slotsLoading ? (
                <div className="loading">Завантаження...</div>
              ) : slots.length === 0 ? (
                <div className="no-slots">
                  <p>Немає вільних слотів на цю дату</p>
                  <button onClick={() => setStep(1)} className="btn-secondary">
                    Обрати іншу дату
                  </button>
                </div>
              ) : (
                <div className="slots-grid-simple">
                  {slots.map((slot, index) => {
                    const isSelected = selectedSlot &&
                      slot.start_time === selectedSlot.start_time &&
                      slot.end_time === selectedSlot.end_time;

                    return (
                      <button
                        key={index}
                        onClick={() => handleSlotSelect(slot)}
                        className={`slot-btn-simple ${isSelected ? 'slot-selected' : ''}`}
                      >
                        <span className="slot-time">{format(new Date(slot.start_time), 'HH:mm')}</span>
                        <span className="slot-icon">{isSelected ? '✓' : '→'}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BookingPage;
