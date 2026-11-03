const api = require('../../utils/api.js');

Page({
  data: {
    step: 'login',
    levels: ['零基础', '初中', '高中', '大学'],
    levelIndex: 1,
    scenes: ['日常交流', '商务洽谈', '工程技术', 'IT', '医疗', '金融'],
    sceneIndex: 0
  },

  onLoad: function () {
    const token = wx.getStorageSync('token');
    if (token) {
      api.setToken(token);
      this.checkProfile();
    }
  },

  // 已登录：判断是否已完成问卷，决定去首页还是先答题
  checkProfile: function () {
    const that = this;
    api.getData().then(function (r) {
      let d = {};
      try { d = JSON.parse(r.data || '{}'); } catch (e) {}
      if (d.profile && d.profile.level !== undefined) {
        wx.reLaunch({ url: '/pages/home/home' });
      } else {
        that.setData({ step: 'questionnaire' });
      }
    }).catch(function () {
      that.setData({ step: 'questionnaire' });
    });
  },

  onWxLogin: function () {
    const that = this;
    wx.login({
      success: function (res) {
        if (!res.code) {
          wx.showToast({ title: '登录失败', icon: 'none' });
          return;
        }
        api.wxlogin(res.code).then(function (r) {
          wx.setStorageSync('token', r.token);
          api.setToken(r.token);
          that.checkProfile();
        }).catch(function (err) {
          wx.showToast({ title: err, icon: 'none' });
        });
      },
      fail: function () {
        wx.showToast({ title: '微信登录调用失败', icon: 'none' });
      }
    });
  },

  onLevelChange: function (e) {
    this.setData({ levelIndex: Number(e.detail.value) });
  },

  onSceneChange: function (e) {
    this.setData({ sceneIndex: Number(e.detail.value) });
  },

  onSubmitQuestionnaire: function () {
    const that = this;
    const level = this.data.levelIndex;
    const scene = this.data.scenes[this.data.sceneIndex];
    api.getData().then(function (r) {
      let d = {};
      try { d = JSON.parse(r.data || '{}'); } catch (e) {}
      d.profile = { level: level, scene: scene };
      return api.putData(d);
    }).then(function () {
      wx.reLaunch({ url: '/pages/home/home' });
    }).catch(function (err) {
      wx.showToast({ title: err, icon: 'none' });
    });
  }
});
