// Modal Logic for Danger Zone
function showDeleteModal() {
    document.getElementById('deleteModal').style.display = 'flex';
}

function hideModal() {
    document.getElementById('deleteModal').style.display = 'none';
}

// Close modal if user clicks outside of it
window.onclick = function(event) {
    let modal = document.getElementById('deleteModal');
    if (event.target == modal) {
        hideModal();
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('adminSidebar');
    const content = document.getElementById('mainContent');
    const icon = document.getElementById('toggleIcon');

    sidebar.classList.toggle('collapsed');
    content.classList.toggle('expanded');

    // आयकॉन फिरवण्यासाठी
    if (sidebar.classList.contains('collapsed')) {
        icon.classList.replace('fa-chevron-left', 'fa-chevron-right');
        localStorage.setItem('sidebarStatus', 'collapsed');
    } else {
        icon.classList.replace('fa-chevron-right', 'fa-chevron-left');
        localStorage.setItem('sidebarStatus', 'expanded');
    }
}

// पेज लोड झाल्यावर जुनी स्थिती टिकवून ठेवणे
window.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('sidebarStatus') === 'collapsed') {
        toggleSidebar();
    }
});
