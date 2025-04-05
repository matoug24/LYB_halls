document.addEventListener('DOMContentLoaded', function () {
    console.log("DEBUG: DOM Loaded, script running.");

    // === IMAGE CAROUSEL ===
    const carouselSlides = document.querySelectorAll('#image-carousel .carousel-slide');
    let currentSlideIndex = 0;
    const slideInterval = 4000;
    
    function showNextSlide() {
        if (carouselSlides.length === 0) return;
    
        carouselSlides[currentSlideIndex]?.classList.remove('active');
        currentSlideIndex = (currentSlideIndex + 1) % carouselSlides.length;
        carouselSlides[currentSlideIndex]?.classList.add('active');
    }
    
    // ✅ Force first slide active (in case HTML doesn't add the class)
    if (carouselSlides.length > 0) {
        carouselSlides.forEach((slide, index) => {
            if (index === 0) {
                slide.classList.add('active');
            } else {
                slide.classList.remove('active');
            }
        });
    }
    
    if (carouselSlides.length > 1) {
        setInterval(showNextSlide, slideInterval);
    }
    

    // === DYNAMIC CALENDAR WITH DROPDOWN ===
    const calendarContainer = document.getElementById('calendar-container');
    const hallSelector = document.getElementById('calendar-hall-select');

    let currentHall = hallSelector ? hallSelector.value : null;
    let currentMonthIndex = 0;

    function renderCalendarForHall(hall, index) {
        if (!calendarData || !calendarData[hall] || !calendarData[hall][index]) {
            console.error("Missing calendar data for", hall, "month index", index);
            return;
        }

        const cal = calendarData[hall][index];
        const monthStr = cal.month.toString().padStart(2, '0');

        let html = `
            <div class="calendar-header">
                <button id="prev-month" aria-label="Previous Month"><</button>
                <span id="month-year">${cal.year}-${monthStr}</span>
                <button id="next-month" aria-label="Next Month">></button>
            </div>
            <div class="calendar-weekdays">
                <div>Sun</div><div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div>
            </div>
            <div class="calendar-days">
        `;

        for (let week of cal.weeks) {
            for (let day of week) {
                if (!day) {
                    html += `<div class="calendar-day other-month"></div>`;
                } else {
                    const booked = day.status === '#f8d7da';
                    const style = `background-color: ${day.status};${booked ? 'color: #721c24;' : ''}`;
                    html += `<div class="calendar-day" style="${style}"><span>${day.day}</span></div>`;
                }
            }
        }

        html += '</div>'; // close calendar-days
        calendarContainer.innerHTML = html;

        // Hook up month nav buttons
        document.getElementById('prev-month').addEventListener('click', () => {
            if (currentMonthIndex > 0) {
                currentMonthIndex--;
                renderCalendarForHall(currentHall, currentMonthIndex);
            }
        });

        document.getElementById('next-month').addEventListener('click', () => {
            if (currentMonthIndex < calendarData[currentHall].length - 1) {
                currentMonthIndex++;
                renderCalendarForHall(currentHall, currentMonthIndex);
            }
        });
    }

    if (hallSelector && calendarContainer) {
        renderCalendarForHall(currentHall, currentMonthIndex);

        hallSelector.addEventListener('change', function () {
            currentHall = this.value;
            currentMonthIndex = 0;
            renderCalendarForHall(currentHall, currentMonthIndex);
        });
    }

    // === SMOOTH SCROLLING FOR NAV LINKS ===
    const navLinks = document.querySelectorAll('.nav-links a');
    const navbar = document.querySelector('.navbar');

    navLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const target = document.getElementById(href.slice(1));
                if (target) {
                    const offset = target.getBoundingClientRect().top + window.scrollY - (navbar?.offsetHeight || 70);
                    window.scrollTo({ top: offset, behavior: 'smooth' });
                }
            }
        });
    });

    // === BOOKING FORM HANDLING (SIMULATED) ===
    const bookingForm = document.getElementById('booking-form');
    const bookingStatus = document.getElementById('booking-status');
    const formHallSelect = document.getElementById('hall-select');

    if (bookingForm && bookingStatus) {
        bookingForm.addEventListener('submit', function (event) {
            event.preventDefault();

            const date = document.getElementById('booking-date')?.value;
            const name = document.getElementById('name')?.value;
            const email = document.getElementById('email')?.value;

            if (!date || !name || !email) {
                alert('Please fill in all required fields (Date, Name, Email).');
                return;
            }

            // You can send this data to the backend via fetch/AJAX here if needed

            bookingForm.style.display = 'none';
            bookingStatus.style.display = 'block';
        });
    }
});
