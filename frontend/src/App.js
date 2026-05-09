import React, { useState, useEffect } from 'react';
import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import ErrorBoundary from './components/ErrorBoundary';
import BookingPage from './pages/BookingPage';
import AdminPage from './pages/AdminPage';
import NotFound from './pages/NotFound';
import { getAdminToken, getUserPhone, clearUserSession, clearAdminSession } from './utils/storage';
import { getUserProfile } from './services/userService';
import './styles/App.css';

function App() {
  const [currentPage, setCurrentPage] = useState(() => {
    const path = window.location.pathname;
    if (path === '/404') return 'notfound';
    if (path.includes('admin')) return 'admin';
    return 'booking';
  });

  const [userVerified, setUserVerified] = useState(() => !!getUserPhone());
  const [userName, setUserName] = useState('');
  const [adminLoggedIn, setAdminLoggedIn] = useState(() => !!getAdminToken());

  // Update URL when page changes
  useEffect(() => {
    const paths = {
      booking: '/',
      admin: '/admin',
      notfound: '/404'
    };
    const newPath = paths[currentPage] || '/';
    if (window.location.pathname !== newPath) {
      window.history.pushState({}, '', newPath);
    }
  }, [currentPage]);

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname;
      if (path === '/404') setCurrentPage('notfound');
      else if (path.includes('admin')) setCurrentPage('admin');
      else setCurrentPage('booking');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Update userVerified when it changes
  useEffect(() => {
    const phone = getUserPhone();
    setUserVerified(!!phone);

    // Fetch user profile to get name
    if (phone) {
      getUserProfile(phone)
        .then(profile => {
          setUserName(profile.name || '');
        })
        .catch(err => {
          console.error('Error fetching user profile:', err);
        });
    } else {
      setUserName('');
    }
  }, []);

  const handleUserLogout = () => {
    setUserVerified(false);
    setUserName('');
    clearUserSession();
    window.location.reload();
  };

  const handleAdminLogout = () => {
    clearAdminSession();
    setAdminLoggedIn(false);
    setCurrentPage('booking');
    toast.info('Ви вийшли з адмін-панелі');
  };

  const renderContent = () => {
    switch (currentPage) {
      case 'admin':
        return <AdminPage onLogout={handleAdminLogout} onLogin={() => setAdminLoggedIn(true)} />;
      case 'notfound':
        return <NotFound onNavigate={setCurrentPage} />;
      case 'booking':
      default:
        return <BookingPage onUserVerified={() => setUserVerified(true)} />;
    }
  };

  return (
    <ErrorBoundary>
      <div className="App">
        <nav className="main-nav">
          <div className="app-header">
            <img src="/doctor.png" alt="Олег Гнідан" className="doctor-photo" />
            <h1 className="app-title">
              {currentPage === 'admin' ? 'Адмін-панель' : 'Запис до лікаря Олега Гнідана'}
            </h1>
          </div>
          <div className="nav-buttons">
            <button
              className={currentPage === 'booking' ? 'active' : ''}
              onClick={() => setCurrentPage('booking')}
            >
              Запис на прийом
            </button>
            <button
              className={currentPage === 'admin' ? 'active' : ''}
              onClick={() => setCurrentPage('admin')}
            >
              Адмін-панель
            </button>
          </div>

          {currentPage === 'booking' && userVerified && userName && (
            <div className="user-name-center">
              <span className="user-name-display">👤 {userName}</span>
            </div>
          )}

          <div className="nav-controls">
            {currentPage === 'booking' && userVerified && (
              <button onClick={handleUserLogout} className="logout-nav-button">
                🚪 Вийти
              </button>
            )}
            {currentPage === 'admin' && adminLoggedIn && (
              <button onClick={handleAdminLogout} className="logout-nav-button">
                🚪 Вийти
              </button>
            )}
          </div>
        </nav>

        {renderContent()}

        <ToastContainer
          position="top-right"
          autoClose={5000}
          hideProgressBar={false}
          newestOnTop
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="dark"
        />
      </div>
    </ErrorBoundary>
  );
}

export default App;
