document.addEventListener('DOMContentLoaded', () => {
  const sidebarToggle = document.querySelector('.menu-toggle');
  const closeSidebar = () => {
    document.body.classList.remove('nav-open');
    sidebarToggle?.setAttribute('aria-expanded', 'false');
  };
  sidebarToggle?.addEventListener('click', () => {
    const open = document.body.classList.toggle('nav-open');
    sidebarToggle.setAttribute('aria-expanded', String(open));
  });

  const navigationGroups = [...document.querySelectorAll('.app-nav-group')];
  navigationGroups.forEach(group => {
    const trigger = group.querySelector('.app-nav-trigger');
    trigger?.addEventListener('click', event => {
      event.stopPropagation();
      navigationGroups.filter(item => item !== group).forEach(item => {
        item.classList.remove('is-open');
        item.querySelector('.app-nav-trigger')?.setAttribute('aria-expanded', 'false');
      });
      const open = group.classList.toggle('is-open');
      trigger.setAttribute('aria-expanded', String(open));
    });
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.app-nav-group')) navigationGroups.forEach(group => {
      group.classList.remove('is-open');
      group.querySelector('.app-nav-trigger')?.setAttribute('aria-expanded', 'false');
    });
    if (window.innerWidth <= 1024 && document.body.classList.contains('nav-open') &&
        !event.target.closest('.sidebar') && !event.target.closest('.menu-toggle')) {
      closeSidebar();
    }
  });
  document.querySelectorAll('.workspace-nav a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 1024) closeSidebar();
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      const catalogSearch = document.querySelector('.header-search input');
      if (catalogSearch && window.getComputedStyle(catalogSearch.closest('.header-search')).display !== 'none') {
        event.preventDefault();
        catalogSearch.focus();
      }
    }
    if (event.key === 'Escape') {
      closeSidebar();
      navigationGroups.forEach(group => {
        group.classList.remove('is-open');
        group.querySelector('.app-nav-trigger')?.setAttribute('aria-expanded', 'false');
      });
    }
  });

  document.querySelectorAll('.messages .alert').forEach((alert, index) => {
    alert.setAttribute('role', 'status');
    alert.querySelector('.alert-dismiss')?.addEventListener('click', () => alert.remove());
    window.setTimeout(() => alert.classList.add('alert-hide'), 5200 + index * 300);
  });

  const passwordToggle = document.getElementById('toggle-password');
  passwordToggle?.addEventListener('click', () => {
    const input = document.getElementById('id_password');
    if (!input) return;
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    passwordToggle.textContent = showing ? 'Show' : 'Hide';
    passwordToggle.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
  });

  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const permissionForm = document.querySelector('[data-permission-form]');
  if (permissionForm) {
    const roleSelect = permissionForm.querySelector('#id_role');
    const permissionInputs = {
      view: permissionForm.querySelector('#id_can_view'),
      add: permissionForm.querySelector('#id_can_add'),
      change: permissionForm.querySelector('#id_can_change'),
      delete: permissionForm.querySelector('#id_can_delete'),
    };
    const applyRolePreset = () => {
      const staffRole = ['library', 'superadmin'].includes(roleSelect?.value);
      if (permissionInputs.view) permissionInputs.view.checked = true;
      ['add', 'change', 'delete'].forEach(action => {
        if (permissionInputs[action]) permissionInputs[action].checked = staffRole;
      });
    };
    roleSelect?.addEventListener('change', applyRolePreset);
  }

  document.querySelectorAll('img').forEach(image => {
    image.addEventListener('error', () => image.classList.add('image-unavailable'), { once: true });
  });

  if (typeof DataTable === 'undefined') return;

  document.querySelectorAll('.js-data-table').forEach((table) => {
    const pageLength = Number(table.dataset.pageLength || 10);
    const orderColumn = Number(table.dataset.orderColumn || 0);
    const orderDirection = table.dataset.orderDirection || 'asc';
    const hasActions = table.dataset.actionsColumn === 'true';

    new DataTable(table, {
      responsive: true,
      pageLength,
      order: [[orderColumn, orderDirection]],
      columnDefs: hasActions ? [{ targets: -1, orderable: false, searchable: false }] : [],
      layout: {
        topStart: 'pageLength',
        topEnd: 'search',
        bottomStart: 'info',
        bottomEnd: 'paging',
      },
      language: {
        search: '',
        searchPlaceholder: 'Search records…',
        lengthMenu: 'Show _MENU_',
        emptyTable: 'No records are available',
      },
    });
  });
});
