const api = require('../../utils/api.js');
const dateUtil = require('../../utils/date.js');

Page({
  data: {
    nickname: '微信用户',
    avatar: '微',
    levelText: '初中',
    streak: 0,
    masteredCount: 0,
    totalDays: 0,
    showBind: false,
    phone: '',
    email: '',
    password: '',
    bindMsg: '',
    menuGroups: []
  },

  onShow: function () {
    this.load();
  },

  load: function () {
    const that = this;
    api.getData().then(function (r) {
      let d = {};
      try { d = JSON.parse(r.data || '{}'); } catch (e) {}
      const profile = d.profile || {};
      const levels = ['零基础', '初中', '高中', '大学'];
      const study = d.studyDays || {};
      const mastered = d.mastered || {};
      that.setData({
        levelText: levels[(profile.level !== undefined) ? profile.level : 1],
        streak: that.calcStreak(study),
        totalDays: Object.keys(study).length,
        masteredCount: Object.keys(mastered).length
      });
    }).catch(function () {});

    api.me().then(function (r) {
      const nick = r.user.nickname || '微信用户';
      that.setData({ nickname: nick, avatar: nick.charAt(0) });
    }).catch(function () {});

    that.setData({
      menuGroups: [
        {
          key: 'study',
          items: [
            { key: 'settings', text: '学习设置（阶段/场景）', path: '' },
            { key: 'bind', text: '绑定手机 / 邮箱', path: '' }
          ]
        },
        {
          key: 'account',
          items: [
            { key: 'logout', text: '退出登录', path: '' }
          ]
        }
      ]
    });
  },

  calcStreak: function (study) {
    let s = 0;
    const d = new Date();
    const key = dateUtil.localDateKey;
    if (!study[key(d)]) { d.setDate(d.getDate() - 1); }
    while (study[key(d)]) { s++; d.setDate(d.getDate() - 1); }
    return s;
  },

  noop: function () {},

  onMenuTap: function (e) {
    const key = e.currentTarget.dataset.key;
    if (key === 'bind') {
      this.setData({ showBind: true, bindMsg: '' });
      return;
    }
    if (key === 'logout') {
      this.onLogout();
      return;
    }
    if (key === 'settings') {
      wx.showToast({ title: '请在首页重新答题，或后续版本开放设置页', icon: 'none' });
      return;
    }
    wx.showToast({ title: '该功能暂未接入', icon: 'none' });
  },

  onBindInput: function (e) {
    const f = e.currentTarget.dataset.field;
    if (f === 'phone') {
      this.setData({ phone: e.detail.value });
    } else if (f === 'email') {
      this.setData({ email: e.detail.value });
    } else if (f === 'password') {
      this.setData({ password: e.detail.value });
    }
  },

  onSubmitBind: function () {
    const that = this;
    api.bind({
      phone: that.data.phone,
      email: that.data.email,
      password: that.data.password
    }).then(function () {
      that.setData({ showBind: false, bindMsg: '', phone: '', email: '', password: '' });
      wx.showToast({ title: '绑定成功', icon: 'success' });
    }).catch(function (err) {
      that.setData({ bindMsg: err });
      wx.showToast({ title: err, icon: 'none' });
    });
  },

  onCloseBind: function () {
    this.setData({ showBind: false });
  },

  onLogout: function () {
    api.logout().catch(function () {});
    wx.removeStorageSync('token');
    api.setToken('');
    wx.reLaunch({ url: '/pages/login/login' });
  }
});
