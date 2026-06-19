import React, { useState, useEffect } from 'react';
import { sendOTP, verifyOTP } from '../services/userService';
import { toast } from 'react-toastify';
import { ButtonLoading } from './Loading';
import '../styles/OTPModal.css';

const OTPModal = ({ phone, setPhone, onVerified, onClose }) => {
  const [otpSent, setOtpSent] = useState(false);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);

  // Check if we're in development mode and should skip OTP
  const isDevelopmentSkipOTP = process.env.NODE_ENV === 'development';

  // ESC to close
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && !loading) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [loading, onClose]);

  const handleSendOTP = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await sendOTP(phone);
      setOtpSent(true);

      // In development mode, show a hint
      if (isDevelopmentSkipOTP) {
        toast.info('Режим розробки: введіть будь-який код');
      } else {
        toast.success('Код відправлено на ваш телефон');
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Помилка відправлення коду');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await verifyOTP(phone, code);
      toast.success('Телефон підтверджено');
      onVerified();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Невірний код');
    } finally {
      setLoading(false);
    }
  };

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget && !loading) {
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="modal-content">
        <button className="modal-close" onClick={onClose} disabled={loading}>×</button>

        <h2>Підтвердження телефону</h2>

        {!otpSent ? (
          <form onSubmit={handleSendOTP}>
            <div className="form-group">
              <label>Номер телефону</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+380501234567"
                required
                pattern="^\+380\d{9}$"
                title="Формат: +380XXXXXXXXX"
                disabled={loading}
                autoFocus
              />
              <p className="telegram-hint">
                💬 Або отримайте OTP через{' '}
                <a
                  href="https://t.me/hnidan_bot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="telegram-link"
                >
                  Telegram Bot @hnidan_bot
                </a>
              </p>
            </div>
            <ButtonLoading type="submit" loading={loading}>
              Отримати код
            </ButtonLoading>
          </form>
        ) : (
          <form onSubmit={handleVerifyOTP}>
            <div className="form-group">
              <label>Введіть код з SMS</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                maxLength="6"
                required
                pattern="\d{6}"
                disabled={loading}
                autoFocus
              />
            </div>
            <ButtonLoading type="submit" loading={loading}>
              Підтвердити
            </ButtonLoading>
            <button
              type="button"
              onClick={() => setOtpSent(false)}
              className="secondary"
              disabled={loading}
            >
              Змінити номер
            </button>
          </form>
        )}

        <p className="modal-hint">
          <kbd>ESC</kbd> для закриття
        </p>
      </div>
    </div>
  );
};

export default OTPModal;
