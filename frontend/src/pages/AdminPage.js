import React, { useState, useEffect, useCallback } from 'react';
import {
  adminLogin,
  getAllAppointments,
  updateAppointment,
  cancelAppointmentAdmin,
  deleteAppointment,
  getAllUsers,
  updateBlacklist,
  updateUserNotes,
  generateReport,
  getDashboardStats,
  exportPDF,
  exportExcel
} from '../services/adminService';
import { addDays, format } from 'date-fns';
import { uk } from 'date-fns/locale';
import { toast } from 'react-toastify';
import SearchBar from '../components/SearchBar';
import Pagination from '../components/Pagination';
import Dashboard from '../components/Dashboard';
import AdminScheduleView from '../components/AdminScheduleView';
import { SkeletonTable } from '../components/Loading';
import { getAdminToken, saveAdminSession } from '../utils/storage';
import '../styles/AdminPage.css';

const AdminPage = ({ onLogout, onLogin }) => {
  const getDefaultReportDates = () => ({
    from: format(new Date(), 'yyyy-MM-dd'),
    to: format(addDays(new Date(), 1), 'yyyy-MM-dd')
  });

  const [authenticated, setAuthenticated] = useState(() => !!getAdminToken());
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
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
  const [reportFromDate, setReportFromDate] = useState(() => getDefaultReportDates().from);
  const [reportToDate, setReportToDate] = useState(() => getDefaultReportDates().to);

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

  const handleLogin = async (e) => {
    e.preventDefault();

    if (!username || !password) {
      toast.error('Введіть логін та пароль');
      return;
    }

    setLoading(true);

    try {
      const result = await adminLogin(username, password);

      if (result.session_token) {
        saveAdminSession(username, result.session_token);
        setAuthenticated(true);
        if (onLogin) onLogin();
        toast.success('Вхід виконано');

        loadDashboardStats();
        loadAppointments();
        loadUsers();
      } else {
        toast.error('Помилка входу');
      }
    } catch (error) {
      toast.error('Невірний логін або пароль');
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

  const handleUpdateUserNotes = async (userId, notes) => {
    try {
      await updateUserNotes(userId, notes);
      toast.success('Нотатки пацієнта оновлено');
      // Update local state
      setUsers(users.map(u => u.id === userId ? { ...u, notes } : u));
      if (selectedUser && selectedUser.id === userId) {
        setSelectedUser({ ...selectedUser, notes });
      }
    } catch (error) {
      toast.error('Помилка оновлення нотаток');
    }
  };

  const handleGenerateReport = async () => {
    if (!reportFromDate || !reportToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const data = await generateReport(reportFromDate, reportToDate);
      const newWindow = window.open();
      newWindow.document.write(data.html);
    } catch (error) {
      toast.error('Помилка генерації звіту');
    }
  };

  const handleExportPDF = async () => {
    if (!reportFromDate || !reportToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const blob = await exportPDF(reportFromDate, reportToDate);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `appointments_${reportFromDate}_${reportToDate}.pdf`;
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
    if (!reportFromDate || !reportToDate) {
      toast.error('Виберіть діапазон дат');
      return;
    }

    try {
      const blob = await exportExcel(reportFromDate, reportToDate);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `appointments_${reportFromDate}_${reportToDate}.xlsx`;
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
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label>Логін</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Введіть логін"
                required
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>Пароль</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введіть пароль"
                required
              />
            </div>
            <button type="submit" disabled={loading}>
              {loading ? 'Вхід...' : 'Увійти'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
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
                        <div className="user-name-row">
                          <p className="user-name"><strong>{user.name}</strong></p>
                          {user.notes && user.notes.trim() && (
                            <span className="user-has-notes" title={user.notes}>📝</span>
                          )}
                        </div>
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
                  <div className="user-header-card">
                    <div className="user-main-info">
                      <div className="user-avatar">
                        <span className="avatar-icon">👤</span>
                      </div>
                      <div className="user-details">
                        <h2>{selectedUser.name}</h2>
                        <div className="user-contact-info">
                          <span className="info-item">
                            <span className="info-icon">📱</span>
                            {selectedUser.phone}
                          </span>
                          <span className="info-item">
                            <span className="info-icon">🎂</span>
                            {format(new Date(selectedUser.birthdate), 'dd.MM.yyyy')}
                            <span className="age-label">
                              ({Math.floor((new Date() - new Date(selectedUser.birthdate)) / (365.25 * 24 * 60 * 60 * 1000))} років)
                            </span>
                          </span>
                        </div>
                      </div>
                      <div className="user-actions">
                        {selectedUser.is_blacklisted ? (
                          <div className="status-section">
                            <span className="user-status-banned">🚫 Заблоковано</span>
                            <button
                              onClick={() => handleToggleBlacklist(selectedUser.id, selectedUser.is_blacklisted)}
                              className="btn-unban-user"
                            >
                              ✓ Розблокувати
                            </button>
                          </div>
                        ) : (
                          <div className="status-section">
                            <span className="user-status-active">✅ Активний</span>
                            <button
                              onClick={() => handleToggleBlacklist(selectedUser.id, selectedUser.is_blacklisted)}
                              className="btn-ban-user"
                            >
                              🚫 Заблокувати
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Patient Notes Section - More compact */}
                    <div className="patient-notes-compact">
                      <div className="notes-header">
                        <span className="notes-icon">📋</span>
                        <span className="notes-title">Нотатки про пацієнта</span>
                      </div>
                      <textarea
                        className="patient-notes-textarea"
                        placeholder="Алергії, протипоказання, особливості лікування..."
                        defaultValue={selectedUser.notes || ''}
                        onBlur={(e) => handleUpdateUserNotes(selectedUser.id, e.target.value)}
                        rows="2"
                      />
                    </div>
                  </div>
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
                value={reportFromDate}
                onChange={(e) => setReportFromDate(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label>До</label>
              <input
                type="date"
                value={reportToDate}
                onChange={(e) => setReportToDate(e.target.value)}
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
