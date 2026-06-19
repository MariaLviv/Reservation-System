import React, { useState, useEffect, useCallback } from 'react';
import Calendar from 'react-calendar';
import { format, addMonths, isBefore, startOfDay, addDays, isSameDay, parseISO } from 'date-fns';
import { uk } from 'date-fns/locale';
import { getAvailableSlots, getDaysOff } from '../services/userService';
import { toast } from 'react-toastify';
import { Spinner } from './Loading';
import 'react-calendar/dist/Calendar.css';
import '../styles/SlotPicker.css';

const SlotPicker = ({ onSlotSelect }) => {
  const [selectedDate, setSelectedDate] = useState(null);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [daysOff, setDaysOff] = useState([]);

  const maxDate = addMonths(new Date(), 6);

  const fetchDaysOff = async () => {
    try {
      const data = await getDaysOff();
      console.log('Days off API response:', data);
      const dates = data.map(d => {
        const parsed = parseISO(d.date);
        console.log('Parsed date:', parsed, 'Original:', d.date);
        return parsed;
      });
      console.log('Days off loaded:', dates);
      setDaysOff(dates);
    } catch (error) {
      console.error('Error fetching days off:', error);
    }
  };

  const isDayOff = (date) => {
    console.log('Checking if day off:', date, 'Against:', daysOff);
    const result = daysOff.some(dayOff => {
      const same = isSameDay(startOfDay(dayOff), startOfDay(date));
      if (same) {
        console.log('Match found:', dayOff, date);
      }
      return same;
    });
    return result;
  };

  const findFirstAvailableDate = async () => {
    let checkDate = new Date();
    const maxCheckDate = addDays(new Date(), 30); // Check up to 30 days ahead

    while (isBefore(checkDate, maxCheckDate)) {
      try {
        const dateStr = format(checkDate, 'yyyy-MM-dd');
        const data = await getAvailableSlots(dateStr, dateStr);
        if (data && data.length > 0) {
          setSelectedDate(checkDate);
          return;
        }
      } catch (error) {
        console.error('Error checking date:', error);
      }
      checkDate = addDays(checkDate, 1);
    }

    // If no slots found in 30 days, just select today
    setSelectedDate(new Date());
  };

  const fetchSlots = useCallback(async () => {
    setLoading(true);
    try {
      const fromDate = format(selectedDate, 'yyyy-MM-dd');
      const toDate = format(selectedDate, 'yyyy-MM-dd');

      const data = await getAvailableSlots(fromDate, toDate);
      setSlots(data);
    } catch (error) {
      toast.error('Помилка завантаження слотів');
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  // Fetch days off on mount
  useEffect(() => {
    fetchDaysOff();
    findFirstAvailableDate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedDate) {
      fetchSlots();
    }
  }, [selectedDate, fetchSlots]);

  const tileDisabled = ({ date }) => {
    // Disable days off
    if (isDayOff(date)) return true;

    // Disable dates beyond max date
    if (isBefore(maxDate, startOfDay(date))) return true;

    // Disable past dates
    if (isBefore(date, startOfDay(new Date()))) return true;

    return false;
  };

  const tileClassName = ({ date, view }) => {
    if (view === 'month' && isDayOff(date)) {
      return 'day-off-tile';
    }
    return null;
  };

  return (
    <div className="slot-picker">
      <h2>Виберіть дату та час</h2>

      {!selectedDate ? (
        <div className="slots-loading">
          <Spinner size="medium" />
          <p>Пошук доступних дат...</p>
        </div>
      ) : (
        <div className="slot-picker-layout">
          <div className="calendar-section">
            <Calendar
              onChange={setSelectedDate}
              value={selectedDate}
              tileDisabled={tileDisabled}
              tileClassName={tileClassName}
              locale="uk-UA"
              minDate={new Date()}
              maxDate={maxDate}
            />
          </div>

          <div className="slots-section">
            <div className="slots-container">
              <h3>Доступні слоти на {format(selectedDate, 'dd MMMM yyyy', { locale: uk })}</h3>

              {loading ? (
                <div className="slots-loading">
                  <Spinner size="medium" />
                  <p>Завантаження слотів...</p>
                </div>
              ) : slots.length > 0 ? (
                <div className="slots-grid">
                  {slots.map((slot, index) => (
                    <button
                      key={index}
                      className="slot-button"
                      onClick={() => onSlotSelect(slot.start_time)}
                    >
                      {format(new Date(slot.start_time), 'HH:mm')}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="no-slots-message">Немає доступних слотів на цей день</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SlotPicker;
