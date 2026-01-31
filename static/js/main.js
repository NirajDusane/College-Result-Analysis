/**
 * Leadger Project - Main JavaScript
 * This script handles theme management, advanced student data filtering,
 * table sorting, loading states, chat interactions, and UI components.
 */

// ---------------------------------------------------
// 1. THEME MANAGEMENT
// ---------------------------------------------------

/**
 * Toggles the application theme between Light and Dark mode.
 * Persists the selection in local storage and updates the data-theme attribute.
 */
function toggleTheme() {
  try {
    const body = document.documentElement;
    const checkbox = document.getElementById("checkbox");
    const currentTheme = body.getAttribute("data-theme");

    if (currentTheme === "dark") {
      body.setAttribute("data-theme", "light");
      localStorage.setItem("theme", "light");
      if (checkbox) checkbox.checked = false;
    } else {
      body.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
      if (checkbox) checkbox.checked = true;
    }
  } catch (error) {
    console.error("Error toggling theme:", error);
  }
}

/**
 * Page initialization logic for themes and UI notifications.
 * Runs once the DOM is fully loaded.
 */
document.addEventListener("DOMContentLoaded", () => {
  try {
    // Initialize theme from local storage
    const savedTheme = localStorage.getItem("theme") || "light";
    const checkbox = document.getElementById("checkbox");
    document.documentElement.setAttribute("data-theme", savedTheme);
    if (checkbox) checkbox.checked = savedTheme === "dark";

    // Logic for handling flash message/toast auto-dismissal
    const toasts = document.querySelectorAll(".toast-card");
    toasts.forEach((toast) => {
      // Auto-dismiss message after 5 seconds
      setTimeout(() => {
        toast.classList.add("toast-exit"); // Trigger exit animation
        setTimeout(() => {
          toast.remove(); // Remove element from DOM
        }, 400);
      }, 5000);
    });
  } catch (error) {
    console.error("Initialization error:", error);
  }
});

// ---------------------------------------------------
// 2. LOADING ANIMATION CONTROL
// ---------------------------------------------------

/**
 * Toggles the visibility of the global loader overlay.
 * @param {boolean} status - True to display the loader, False to hide it.
 */
function showLoader(status) {
  try {
    const loader = document.getElementById("loader-overlay");
    if (loader) {
      loader.style.display = status ? "flex" : "none";
    }
  } catch (error) {
    console.error("Loader control error:", error);
  }
}

/**
 * Automatically displays the loader during form submissions.
 */
document.addEventListener("submit", () => {
  showLoader(true);
});

// ---------------------------------------------------
// 3. ADVANCED FILTERING LOGIC
// ---------------------------------------------------

/**
 * Filters the student table based on search input, status, gender, and academic performance.
 * Includes logic for specialized categories like 'toppers'.
 */
function globalFilter() {
  showLoader(true);

  setTimeout(() => {
    try {
      const searchText = document
        .getElementById("searchInput")
        .value.toUpperCase();
      const filterVal = document.getElementById("statusFilter").value;
      const tableBody = document.getElementById("studentTableBody");

      if (!tableBody) {
        showLoader(false);
        return;
      }

      const rows = Array.from(tableBody.querySelectorAll("tr"));

      // Reset visibility
      rows.forEach((row) => (row.style.display = "none"));

      let visibleRows = rows.filter((row) => {
        const text = row.textContent.toUpperCase();
        const gender = row.getAttribute("data-gender");
        const status = row.getAttribute("data-status");
        const sgpa = parseFloat(row.getAttribute("data-sgpa") || 0);

        let isSearchMatch = text.includes(searchText);
        let isFilterMatch = true;

        // Evaluate specific categorical filters
        switch (filterVal) {
          case "pass":
            isFilterMatch = status === "pass";
            break;
          case "fail":
            isFilterMatch = status === "fail";
            break;
          case "atkt":
            isFilterMatch = status === "atkt";
            break;
          case "male_pass":
            isFilterMatch = gender === "Male" && status === "pass";
            break;
          case "male_atkt":
            isFilterMatch = gender === "Male" && status === "atkt";
            break;
          case "male_fail":
            isFilterMatch = gender === "Male" && status === "fail";
            break;
          case "female_pass":
            isFilterMatch = gender === "Female" && status === "pass";
            break;
          case "female_atkt":
            isFilterMatch = gender === "Female" && status === "atkt";
            break;
          case "female_fail":
            isFilterMatch = gender === "Female" && status === "fail";
            break;
          case "distinction":
            isFilterMatch = status === "pass" && sgpa >= 7.75;
            break;
          case "first_class":
            isFilterMatch = status === "pass" && sgpa >= 6.75 && sgpa < 7.75;
            break;
          case "higher_second":
            isFilterMatch = status === "pass" && sgpa >= 6.25 && sgpa < 6.75;
            break;
          case "second_class":
            isFilterMatch = status === "pass" && sgpa >= 5.75 && sgpa < 6.25;
            break;
          case "pass_class":
            isFilterMatch = status === "pass" && sgpa > 0 && sgpa < 5.75;
            break;
          default:
            break;
        }

        return isSearchMatch && isFilterMatch;
      });

      // Handle logic for academic topper categories
      if (filterVal.startsWith("top")) {
        let topperCandidates = rows.filter(
          (r) => r.getAttribute("data-status") === "pass"
        );
        if (filterVal === "top5_male")
          topperCandidates = topperCandidates.filter(
            (r) => r.getAttribute("data-gender") === "Male"
          );
        if (filterVal === "top5_female")
          topperCandidates = topperCandidates.filter(
            (r) => r.getAttribute("data-gender") === "Female"
          );

        topperCandidates.sort(
          (a, b) =>
            parseFloat(b.getAttribute("data-sgpa")) -
            parseFloat(a.getAttribute("data-sgpa"))
        );
        const limit = filterVal === "top3_overall" ? 3 : 5;
        visibleRows = topperCandidates.slice(0, limit);
      }

      // Apply visibility to final filtered set
      visibleRows.forEach((row) => (row.style.display = ""));
    } catch (error) {
      console.error("Global filter execution error:", error);
    } finally {
      showLoader(false);
    }
  }, 500);
}

/**
 * Updates the filter dropdown value and triggers the global filter.
 */
function filterByCard(status) {
  const filterDropdown = document.getElementById("statusFilter");
  if (filterDropdown) {
    filterDropdown.value = status;
    globalFilter();
  }
}

/**
 * Combines gender and status into a single filter action.
 */
function applyGenderStatusFilter(gender, status) {
  const filterDropdown = document.getElementById("statusFilter");
  if (filterDropdown) {
    filterDropdown.value = gender.toLowerCase() + "_" + status;
    globalFilter();
  }
}

/**
 * Clears all active search and categorical filters.
 */
function resetAllFilters() {
  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  if (searchInput) searchInput.value = "";
  if (statusFilter) statusFilter.value = "all";
  globalFilter();
}

// ---------------------------------------------------
// 4. SORTING LOGIC
// ---------------------------------------------------

/**
 * Sorts the student table rows alphabetically or numerically.
 * @param {number} n - The column index to sort by.
 */
function sortTable(n) {
  showLoader(true);
  setTimeout(() => {
    try {
      const table = document.getElementById("studentTable");
      let switching = true,
        i,
        x,
        y,
        shouldSwitch,
        dir = "asc",
        switchcount = 0;

      while (switching) {
        switching = false;
        const rows = table.rows;
        for (i = 1; i < rows.length - 1; i++) {
          shouldSwitch = false;
          x = rows[i].getElementsByTagName("TD")[n];
          y = rows[i + 1].getElementsByTagName("TD")[n];

          let xVal = x.textContent.trim().toLowerCase();
          let yVal = y.textContent.trim().toLowerCase();
          let xNum = parseFloat(xVal),
            yNum = parseFloat(yVal);
          let isNumeric = !isNaN(xNum) && !isNaN(yNum);

          if (dir === "asc") {
            if (isNumeric ? xNum > yNum : xVal > yVal) {
              shouldSwitch = true;
              break;
            }
          } else if (dir === "desc") {
            if (isNumeric ? xNum < yNum : xVal < yVal) {
              shouldSwitch = true;
              break;
            }
          }
        }
        if (shouldSwitch) {
          rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
          switching = true;
          switchcount++;
        } else {
          if (switchcount === 0 && dir === "asc") {
            dir = "desc";
            switching = true;
          }
        }
      }
    } catch (error) {
      console.error("Table sorting error:", error);
    } finally {
      showLoader(false);
    }
  }, 50);
}

// ---------------------------------------------------
// 5. SUBJECT ANALYSIS FILTERS
// ---------------------------------------------------

/**
 * Filters rows based on gender and pass/fail status for subject analysis.
 */
function filterTable(gender, status) {
  showLoader(true);
  setTimeout(() => {
    try {
      const rows = document.querySelectorAll("#studentTableBody tr");
      rows.forEach((row) => {
        const rowGender = row.getAttribute("data-gender");
        const rowStatus = row.getAttribute("data-status").toLowerCase();
        let genderMatch = gender === "all" || rowGender === gender;
        let statusMatch = status === "all" || rowStatus === status;
        row.style.display = genderMatch && statusMatch ? "" : "none";
      });
    } catch (error) {
      console.error("Subject analysis filterTable error:", error);
    } finally {
      showLoader(false);
    }
  }, 100);
}

/**
 * Filters rows based on the specific academic grade classification.
 */
function filterByGradeClass(gradeClass) {
  showLoader(true);
  setTimeout(() => {
    try {
      const rows = document.querySelectorAll("#studentTableBody tr");
      rows.forEach((row) => {
        const rowGradeClass = row.getAttribute("data-grade-class");
        row.style.display =
          gradeClass === "all" || rowGradeClass === gradeClass ? "" : "none";
      });
    } catch (error) {
      console.error("Filter by grade class error:", error);
    } finally {
      showLoader(false);
    }
  }, 100);
}

/**
 * Isolates and displays only the students marked as toppers.
 */
function filterByToppers() {
  showLoader(true);
  setTimeout(() => {
    try {
      const rows = document.querySelectorAll("#studentTableBody tr");
      rows.forEach((row) => {
        const isTopper = row.getAttribute("data-is-topper") === "true";
        row.style.display = isTopper ? "" : "none";
      });
    } catch (error) {
      console.error("Filter by toppers error:", error);
    } finally {
      showLoader(false);
    }
  }, 150);
}

// ---------------------------------------------------
// 6. CHATBOT INTERACTIONS
// ---------------------------------------------------

/**
 * Toggles the visibility of the AI chatbot interface.
 */
function toggleChat() {
  try {
    const box = document.getElementById("chat-box");
    if (box) {
      box.style.display = box.style.display === "none" ? "flex" : "none";
    }
  } catch (error) {
    console.error("Toggle chat error:", error);
  }
}

/**
 * Unused simple chat function.
 * This block is redundant compared to the detailed sendToGemini implementation below.
 * DO NOT DELETE - Kept for reference.
 */
/*
function sendToGemini() {
    const msg = document.getElementById('user-msg').value;
    const content = document.getElementById('chat-content');
    content.innerHTML += `<p><b>You:</b> ${msg}</p>`;
    
    fetch('/ask_chatbox', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
    })
    .then(r => r.json())
    .then(data => {
        content.innerHTML += `<p style="color: var(--accent);"><b>AI:</b> ${data.answer}</p>`;
        document.getElementById('user-msg').value = '';
    });
}
*/

/**
 * Sends a user message to the AI chatbot and displays the processed response.
 */
function sendToGemini() {
  const input = document.getElementById("user-msg");
  const msg = input.value.trim();
  if (!msg) return;

  const content = document.getElementById("chat-content");
  const loader = document.getElementById("chat-loader");

  try {
    // Add User Message UI
    content.innerHTML += `<div class="message user-msg">${msg}</div>`;
    input.value = "";
    loader.style.display = "flex";
    content.scrollTop = content.scrollHeight;

    fetch("/ask_chatbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    })
      .then((r) => r.json())
      .then((data) => {
        loader.style.display = "none";
        content.innerHTML += `<div class="ai-msg">${data.answer.replace(
          /\n/g,
          "<br>"
        )}</div>`;
        content.scrollTop = content.scrollHeight;
      })
      .catch((err) => {
        console.error("Chat communication error:", err);
        loader.style.display = "none";
      });
  } catch (error) {
    console.error("sendToGemini logic error:", error);
  }
}

// ---------------------------------------------------
// 7. REPORTING & UI HELPERS
// ---------------------------------------------------

/**
 * Opens the generated subject report in a new window/tab.
 * @param {string} subjectCode - The unique code of the subject.
 */
function downloadSubjectReport(subjectCode) {
  try {
    const url = `/generate_subject_report/${subjectCode}`;
    window.open(url, "_blank");
  } catch (error) {
    console.error("Report download error:", error);
  }
}

/**
 * Logic to update the report generation link dynamically when a subject is selected.
 */
document.addEventListener("DOMContentLoaded", () => {
  try {
    const subjectSelect = document.getElementById("subjectSelect");
    const printBtn = document.getElementById("printReportBtn");

    if (subjectSelect && printBtn) {
      subjectSelect.addEventListener("change", function () {
        const newSubjectCode = this.value;
        if (newSubjectCode) {
          // Update report link based on selected subject
          const baseUrl = "/generate_subject_report/";
          printBtn.href = baseUrl + newSubjectCode;
          console.log("Report URL updated for Subject: " + newSubjectCode);
        }
      });
    }
  } catch (error) {
    console.error("Subject report listener error:", error);
  }
});

/**
 * Provides a real-time preview of an uploaded signature image.
 * @param {HTMLElement} input - The file input element.
 * @param {string} previewId - The ID of the image element to display the preview.
 */
function previewSig(input, previewId) {
  try {
    const preview = document.getElementById(previewId);
    const file = input.files[0];
    const reader = new FileReader();

    reader.onload = function (e) {
      preview.src = e.target.result;
      preview.style.display = "block"; // Show image after loading
    };

    if (file) {
      reader.readAsDataURL(file);
    }
  } catch (error) {
    console.error("Signature preview error:", error);
  }
}

 /**
 * Dynamic Dropdown Logic:
 * Filters the 'Academic Year' dropdown based on the selected 'Department'.
 */
function updateYearDropdown() {
    const courseSelect = document.getElementById('course_select');
    const yearSelect = document.getElementById('year_select');
    
    // Safety check to ensure elements exist on the current page
    if (!courseSelect || !yearSelect) return;

    const selectedCourse = courseSelect.value;

    // Reset Year Dropdown
    yearSelect.innerHTML = '<option value="">-- Select Year --</option>';
    
    // Check if a course is selected and global data exists
    if (selectedCourse && typeof savedData !== 'undefined') {
        // Filter the database rows for matches
        const filteredRecords = savedData.filter(item => item.course === selectedCourse);
        
        // Add each matching year as an option
        filteredRecords.forEach(record => {
            const option = document.createElement('option');
            option.value = record.year;
            option.textContent = record.year;
            yearSelect.appendChild(option);
        });

        // Enable the dropdown now that it has items
        yearSelect.disabled = false;
    } else {
        // Disable if no department is selected
        yearSelect.innerHTML = '<option value="">-- First Select Department --</option>';
        yearSelect.disabled = true;
    }
}