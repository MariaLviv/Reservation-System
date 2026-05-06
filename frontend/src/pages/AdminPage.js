import React, { useState, useEffect, useCallback } from 'react';
import {
  getAdminPhone,
  sendAdminOTP,
  verifyAdminOTP,
  getAllAppointments,
  updateAppointment,
  cancelAppointmentAdmin,
  deleteAppointment,
  getAllUsers,
  updateBlacklist,
  generateReport,
  getDashboardStats,
  exportPDF,
  exportExcel
} from '../services/adminService';
import { format } from 'date-fns';
import { uk } from 'date-fns/locale';
import { toast } from 'react-toastify';
import SearchBar from '../components/SearchBar';
import Pagination from '../components/Pagination';
import Dashboard from '../components/Dashboard';
import AdminScheduleView from '../components/AdminScheduleView';
import { SkeletonTable } from '../components/Loading';
import { getAdminToken, saveAdminSession } from '../utils/storage';
import '../styles/AdminPage.css';

const AdminPage = ({ onLogout }) => {
  const [adminPhone, setAdminPhone] = useState('');
  const [authenticated, setAuthenticated] = useState(() => !!getAdminToken());
  const [phone, setPhone] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);

  // Admin data
  const [appointments, setAppointments] = useState([]);
  const [appointmentsTotal, setAppointmentsTotal] = useState(0);
  const [appointmentsPage, setAppointmentsPage] = useState(1);
  const [appointmentsPageSize, setAppointmentsPageSize] = useState(10);

  const [users, setUsers] = useState([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const [usersPageSize, setUsersPageSize] = useState(10);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userAppointments, setUserAppointments] = useState([]);

  const [activeTab, setActiveTab] = useState('schedule');
  const [dataLoading, setDataLoading] = useState(false);

  // Dashboard stats
  const [dashboardStats, setDashboardStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Filters for appointments
  const [filterFromDate, setFilterFromDate] = useState('');
  const [filterToDate, setFilterToDate] = useState('');
  const [filterStatus] = useState('');
  const [searchQuery] = useState('');

  // Filters for users
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [userBlacklistFilter] = useState('');

  const loadDashboardStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await getDashboardStats();
      setDashboardStats(data);
    } catch (error) {
      toast.error('Помилка завантаження статистики');
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const loadAppointments = useCallback(async () => {
    setDataLoading(true);
    try {
      const skip = (appointmentsPage - 1) * appointmentsPageSize;
      const data = await getAllAppointments(
        filterFromDate,
        filterToDate,
        filterStatus,
        searchQuery,
        skip,
        appointmentsPageSize
      );
      setAppointments(data.items);
      setAppointmentsTotal(data.total);
    } catch (error) {
      toast.error('Помилка завантаження записів');
    } finally {
      setDataLoading(false);
    }
  }, [appointmentsPage, appointmentsPageSize, filterFromDate, filterToDate, filterStatus, searchQuery]);

  const loadUsers = useCallback(async () => {
    setDataLoading(true);
    try {
      const blacklistValue = userBlacklistFilter === 'true' ? true :
                            userBlacklistFilter === 'false' ? false : undefined;
      const skip = (usersPage - 1) * usersPageSize;
      const data = await getAllUsers(userSearchQuery, blacklistValue, skip, usersPageSize);
      setUsers(data.items);
      setUsersTotal(data.total);
    } catch (error) {
      toast.error('Помилка завантаження користувачів');
    } finally {
      setDataLoading(false);
    }
  }, [usersPage, usersPageSize, userSearchQuery, userBlacklistFilter]);

  useEffect(() => {
    const token = localStorage.getItem('adminToken');
    if (token) {
      setAuthenticated(true);
      loadDashboardStats();
      loadAppointments();
      loadUsers();
    }
  }, [loadDashboardStats, loadAppointments, loadUsers]);

  // Fetch admin phone from backend
  useEffect(() => {
    const fetchAdminPhone = async () => {
      try {
        const phone = await getAdminPhone();
        setAdminPhone(phone);
      } catch (error) {
        console.error('Failed to fetch admin phone');
      }
    };
    if (!authenticated) {
      fetchAdminPhone();
    }
  }, [authenticated]);

  useEffect(() => {
    if (authenticated && activeTab === 'appointments') {
      setAppointmentsPage(1);
      loadAppointments();
    }
  }, [filterFromDate, filterToDate, filterStatus, searchQuery, authenticated, activeTab, loadAppointments]);

  useEffect(() => {
    if (authenticated && activeTab === 'appointments') {
      loadAppointments();
    }
  }, [appointmentsPage, appointmentsPageSize, authenticated, activeTab, loadAppointments]);

  useEffect(() => {
    if (authenticated && activeTab === 'users') {
      setUsersPage(1);
      loadUsers();
    }
  }, [userSearchQuery, userBlacklistFilter, authenticated, activeTab, loadUsers]);

  useEffect(() => {
    if (authenticated && activeTab === 'users') {
      loadUsers();
    }
  }, [usersPage, usersPageSize, authenticated, activeTab, loadUsers]);

  const handleSendOTP = async (e) => {
    e.preventDefault();

    // Check if entered phone matches hardcoded admin phone
    if (phone !== adminPhone) {
      toast.error('Невірний номер адміністратора');
      return;
    }

    setLoading(true);

    try {
      await sendAdminOTP(adminPhone);
      setOtpSent(true);
      toast.success('Код підтвердження надіслано в Telegram');
    } catch (error) {
      toast.error('Помилка відправки коду');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async (e) => {
    e.preventDefault();

    if (!otpCode || otpCode.length !== 6) {
      toast.error('Введіть 6-значний код');
      return;
    }

    setLoading(true);

    try {
      const result = await verifyAdminOTP(adminPhone, otpCode);

      if (result.session_token) {
        saveAdminSession(adminPhone, result.session_token);

        setAuthenticated(true);
        toast.success('Вхід виконано');

        loadDashboardStats();
        loadAppointments();
        loadUsers();
      } else {
        toast.error('Невірний код підтвердження');
      }
    } catch (error) {
      toast.error('Помилка верифікації');
    } finally {
      setLoading(false);
    }
  };

  const loadUserAppointments = async (userId) => {
    try {
      const response = await fetch(`/api/v1/admin/users/${userId}/appointments`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('adminToken')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setUserAppointments(data.appointments);
        setSelectedUser(data.user);
      }
    } catch (error) {
      toast.error('Помилка завантаження записів користувача');
    }
  };

  const handleCancelAppointment = async (id) => {
    if (!window.confirm('Скасувати запис?')) return;

    try {
      await cancelAppointmentAdmin(id);
      toast.success('Запис скасовано');
      loadAppointments();
      loadDashboardStats();
    } catch (error) {
      toast.error('Помилка');
    }
  };

  const handleDeleteAppointment = async (id) => {
    if (!window.confirm('⚠️ УВАГА: Видалити запис назавжди?\n\nЦю дію не можна буде скасувати. Запис буде повністю видалено з бази даних.')) return;

    try {
      await deleteAppointment(id);
      toast.success('Запис видалено назавжди');
      loadAppointments();
      loadDashboardStats();
    } catch (error) {
      toast.error('Помилка видалення');
    }
  };

  const handleToggleBlacklist = async (userId, currentStatus) => {
    const action = currentStatus ? 'розблокувати' : 'заблокувати';
    if (!window.confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} цього користувача?`)) return;

    try {
      await updateBlacklist(userId, !currentStatus);
      toast.success(`Користувача ${currentStatus ? 'розблоковано' : 'заблоковано'}`);
      loadUsers();
      if (selectedUser?.id === userId) {
        loadUserAppointments(userId);
      }
    } catch (error) {
      toast.error('Помилка оновлення статусу');
    }
  };

  const handleUpdateAppointmentNote = async (id, notes) => {
    try {
      await updateAppointment({ appointment_id: id, notes });
      toast.success('Нотатку оновлено');
      loadAppointments();
    } catch (error) {
      toast.error('Помилка');
    }
  };

  const handleGenerateReport = async () => {
    if (!filterFromDate || !filterToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const data = await generateReport(filterFromDate, filterToDate);
      const newWindow = window.open();
      newWindow.document.write(data.html);
    } catch (error) {
      toast.error('Помилка генерації звіту');
    }
  };

  const handleExportPDF = async () => {
    if (!filterFromDate || !filterToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const blob = await exportPDF(filterFromDate, filterToDate);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `appointments_${filterFromDate}_${filterToDate}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast.success('PDF завантажено');
    } catch (error) {
      toast.error('Помилка експорту PDF');
    }
  };

  const handleExportExcel = async () => {
    if (!filterFromDate || !filterToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const blob = await exportExcel(filterFromDate, filterToDate);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `appointments_${filterFromDate}_${filterToDate}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast.success('Excel завантажено');
    } catch (error) {
      toast.error('Помилка експорту Excel');
    }
  };

  if (!authenticated) {
    return (
      <div className="admin-page">
        <header>
          <h1>Адмін-панель</h1>
        </header>
        <div className="admin-login">
          {!otpSent ? (
            <form onSubmit={handleSendOTP}>
              <div className="form-group">
                <label>Номер телефону адміністратора</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\s/g, ''))}
                  placeholder="+380501234567"
                  required
                />
              </div>
              <button type="submit" disabled={loading}>
                {loading ? 'Відправка...' : 'Отримати код'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOTP}>
              <div className="form-group">
                <label>Введіть код з Telegram</label>
                <input
                  type="text"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  required
                  autoFocus
                />
                <p className="otp-hint">
                  Код надіслано на номер {adminPhone}
                </p>
                <p className="telegram-hint">
                  💬 Код приходить через{' '}
                  <a href="https://t.me/Toka_12_bot" target="_blank" rel="noopener noreferrer" className="telegram-link">
                    Telegram Bot @Toka_12_bot
                  </a>
                </p>
              </div>
              <button type="submit" disabled={loading}>
                {loading ? 'Перевірка...' : 'Увійти'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setOtpSent(false);
                  setOtpCode('');
                }}
              >
                ← Змінити номер
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-tabs">
        <button
          className={activeTab === 'schedule' ? 'active' : ''}
          onClick={() => setActiveTab('schedule')}
        >
          Налаштування
        </button>
        <button
          className={activeTab === 'appointments' ? 'active' : ''}
          onClick={() => setActiveTab('appointments')}
        >
          Записи
        </button>
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Статистика
        </button>
        <button
          className={activeTab === 'users' ? 'active' : ''}
          onClick={() => setActiveTab('users')}
        >
          Користувачі
        </button>
        <button
          className={activeTab === 'reports' ? 'active' : ''}
          onClick={() => setActiveTab('reports')}
        >
          Роздрукувати розклад
        </button>
      </div>

      {activeTab === 'dashboard' && (
        <div className="tab-content">
          <Dashboard stats={dashboardStats} loading={statsLoading} />
        </div>
      )}

      {activeTab === 'appointments' && (
        <div className="tab-content">
          <h2>Записи на прийом</h2>

          <div className="filters">
            <input
              type="date"
              value={filterFromDate}
              onChange={(e) => setFilterFromDate(e.target.value)}
              placeholder="Від"
            />
            <input
              type="date"
              value={filterToDate}
              onChange={(e) => setFilterToDate(e.target.value)}
              placeholder="До"
            />
            <button onClick={loadAppointments}>Фільтрувати</button>
          </div>

          {dataLoading ? (
            <SkeletonTable rows={5} />
          ) : (
            <>
              <div className="appointments-table">
                {appointments.map((appointment) => (
                  <div key={appointment.id} className="appointment-row">
                    <div className="appointment-info">
                      <p><strong>{appointment.user?.name}</strong></p>
                      <p>{appointment.user?.phone}</p>
                      <p>{format(new Date(appointment.start_time), 'dd MMMM yyyy, HH:mm', { locale: uk })}</p>
                      <p>Статус: <span className={`status-${appointment.status}`}>{appointment.status}</span></p>
                    </div>

                    <div className="appointment-actions">
                      <textarea
                        placeholder="Нотатки..."
                        defaultValue={appointment.notes || ''}
                        onBlur={(e) => handleUpdateAppointmentNote(appointment.id, e.target.value)}
                      />
                      {appointment.status === 'booked' && (
                        <button onClick={() => handleCancelAppointment(appointment.id)} className="cancel-button">
                          Скасувати
                        </button>
                      )}
                      {appointment.status === 'cancelled' && (
                        <button
                          onClick={() => handleDeleteAppointment(appointment.id)}
                          className="delete-button"
                          title="Видалити запис назавжди з бази даних"
                        >
                          🗑️ Видалити назавжди
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <Pagination
                currentPage={appointmentsPage}
                totalPages={Math.ceil(appointmentsTotal / appointmentsPageSize)}
                totalItems={appointmentsTotal}
                itemsPerPage={appointmentsPageSize}
                onPageChange={setAppointmentsPage}
                onPageSizeChange={(size) => {
                  setAppointmentsPageSize(size);
                  setAppointmentsPage(1);
                }}
              />
            </>
          )}
        </div>
      )}

      {activeTab === 'users' && (
        <div className="tab-content users-with-appointments">
          <div className="users-list-panel">
            <h2>Користувачі</h2>

            <SearchBar onSearch={setUserSearchQuery} placeholder="Пошук за ім'ям або телефоном" />

            {dataLoading ? (
              <SkeletonTable rows={5} />
            ) : (
              <>
                <div className="users-list">
                  {users.map((user) => (
                    <div
                      key={user.id}
                      className={`user-item ${selectedUser?.id === user.id ? 'selected' : ''}`}
                      onClick={() => loadUserAppointments(user.id)}
                    >
                      <div className="user-info">
                        <p className="user-name"><strong>{user.name}</strong></p>
                        <p className="user-phone">{user.phone}</p>
                        <p className="user-birthdate">
                          {format(new Date(user.birthdate), 'dd.MM.yyyy')}
                        </p>
                        {user.is_blacklisted && (
                          <span className="user-blacklisted">🚫 Заблоковано</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                <Pagination
                  currentPage={usersPage}
                  totalPages={Math.ceil(usersTotal / usersPageSize)}
                  totalItems={usersTotal}
                  itemsPerPage={usersPageSize}
                  onPageChange={setUsersPage}
                  onPageSizeChange={(size) => {
                    setUsersPageSize(size);
                    setUsersPage(1);
                  }}
                />
              </>
            )}
          </div>

          <div className="user-appointments-panel">
            {selectedUser ? (
              <>
                <div className="selected-user-header">
                  <h2>{selectedUser.name}</h2>
                  <p>{selectedUser.phone}</p>
                  <p>Дата народження: {format(new Date(selectedUser.birthdate), 'dd.MM.yyyy')}</p>
                  {selectedUser.is_blacklisted ? (
                    <>
                      <span className="user-status-banned">🚫 Заблоковано</span>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-tertiary)', marginTop: '0.5rem' }}>
                        Заблокований користувач не може створювати нові записи
                      </p>
                    </>
                  ) : (
                    <span className="user-status-active">✅ Активний</span>
                  )}
                  <button
                    onClick={() => handleToggleBlacklist(selectedUser.id, selectedUser.is_blacklisted)}
                    className={selectedUser.is_blacklisted ? 'btn-unban-user' : 'btn-ban-user'}
                  >
                    {selectedUser.is_blacklisted ? '✓ Розблокувати' : '🚫 Заблокувати'}
                  </button>
                </div>

                <h3>Записи користувача ({userAppointments.length})</h3>

                {userAppointments.length === 0 ? (
                  <p className="no-appointments">Немає записів</p>
                ) : (
                  <div className="appointments-list">
                    {userAppointments.map((apt) => (
                      <div key={apt.id} className={`appointment-card ${apt.status}`}>
                        <div className="appointment-header-row">
                          <div className="appointment-time">
                            <strong>{format(new Date(apt.start_time), 'dd MMM yyyy', { locale: uk })}</strong>
                            <span>{format(new Date(apt.start_time), 'HH:mm')} - {format(new Date(apt.end_time), 'HH:mm')}</span>
                          </div>
                          <div className="appointment-status">
                            {apt.status === 'booked' ? '✅ Заброньовано' :
                             apt.status === 'cancelled' ? '❌ Скасовано' :
                             apt.status === 'completed' ? '✓ Завершено' : apt.status}
                          </div>
                        </div>
                        <div className="appointment-notes-section">
                          <textarea
                            className="appointment-notes-input"
                            placeholder="Коментар..."
                            defaultValue={apt.notes || ''}
                            onBlur={(e) => handleUpdateAppointmentNote(apt.id, e.target.value)}
                            rows="2"
                          />
                        </div>
                        {apt.status === 'booked' && (
                          <button
                            onClick={() => handleCancelAppointment(apt.id)}
                            className="btn-cancel-appointment"
                          >
                            Скасувати запис
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="no-user-selected">
                <p>Оберіть користувача зі списку ліворуч</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'schedule' && (
        <div className="tab-content">
          <AdminScheduleView />
        </div>
      )}

      {activeTab === 'reports' && (
        <div className="tab-content">
          <h2>Роздрукувати розклад</h2>

          <div className="report-form">
            <div className="form-group">
              <label>Від</label>
              <input
                type="date"
                value={filterFromDate}
                onChange={(e) => setFilterFromDate(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label>До</label>
              <input
                type="date"
                value={filterToDate}
                onChange={(e) => setFilterToDate(e.target.value)}
                required
              />
            </div>

            <div className="report-actions">
              <button onClick={handleGenerateReport} className="btn-primary">
                📄 Переглянути HTML
              </button>
              <button onClick={handleExportPDF} className="btn-success">
                📑 Експорт PDF
              </button>
              <button onClick={handleExportExcel} className="btn-info">
                📊 Експорт Excel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPage;
