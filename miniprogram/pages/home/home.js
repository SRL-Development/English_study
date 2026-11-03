const words = require('../../utils/words.js');
const audio = require('../../utils/audio.js');
const api = require('../../utils/api.js');
const dateUtil = require('../../utils/date.js');

Page({
  data: {
    word: null,
    index: 0,
    total: 0,
    level: 1,
    scene: '日常交流',
    list: [],
    playing: false,
    recording: false,
    score: null,
    wordScores: [],
    streak: 0,
    todayCount: 0,
    status: 'loading'
  },

  onShow: function () {
    this.loadProgressAndWords();
  },

  loadProgressAndWords: function () {
    const that = this;
    that.setData({ status: 'loading' });
    api.getData().then(function (r) {
      let d = {};
      try { d = JSON.parse(r.data || '{}'); } catch (e) {}
      const profile = d.profile || {};
      const level = (profile.level !== undefined) ? profile.level : 1;
      const scene = profile.scene || '日常交流';
      const list = words.pick(level, scene);
      const study = d.studyDays || {};
      const today = dateUtil.localDateKey();
      const todayCount = study[today] || 0;
      const streak = that.calcStreak(study);
      that._store = d;
      if (!list.length) {
        that.setData({ status: 'empty', level: level, scene: scene, streak: streak, todayCount: todayCount });
      } else {
        that.setData({
          status: 'ready', level: level, scene: scene, list: list,
          total: list.length, index: 0, streak: streak, todayCount: todayCount
        });
        that.showWord(0);
      }
    }).catch(function (err) {
      wx.showToast({ title: err, icon: 'none' });
      that.setData({ status: 'empty' });
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

  showWord: function (i) {
    const w = this.data.list[i];
    this.setData({ word: w, index: i, score: null, wordScores: [], playing: false, recording: false });
  },

  onPlay: function () {
    if (!this.data.word) return;
    const that = this;
    that.setData({ playing: true });
    audio.playTTS(that.data.word.word).then(function () {
      that.setData({ playing: false });
    }).catch(function (err) {
      that.setData({ playing: false });
      wx.showToast({ title: err, icon: 'none' });
    });
  },

  onPlaySentence: function () {
    if (!this.data.word) return;
    const that = this;
    that.setData({ playing: true });
    audio.playTTS(that.data.word.example).then(function () {
      that.setData({ playing: false });
    }).catch(function (err) {
      that.setData({ playing: false });
      wx.showToast({ title: err, icon: 'none' });
    });
  },

  onRecord: function () {
    const that = this;
    if (that.data.recording) {
      audio.stopRecord();
      that.setData({ recording: false });
      return;
    }
    that.setData({ recording: true, score: null, wordScores: [] });
    audio.startRecord().then(function (filePath) {
      that.setData({ recording: false });
      wx.showLoading({ title: '评测中...' });
      return audio.assess(that.data.word.word, filePath, 'read_word');
    }).then(function (res) {
      wx.hideLoading();
      if (res.error) {
        wx.showToast({ title: res.error, icon: 'none' });
        return;
      }
      that.setData({ score: res.overall, wordScores: res.words });
    }).catch(function (err) {
      wx.hideLoading();
      that.setData({ recording: false });
      wx.showToast({ title: err, icon: 'none' });
    });
  },

  onKnow: function () { this.mark(true); },
  onUnknown: function () { this.mark(false); },

  mark: function (known) {
    const that = this;
    const w = that.data.word;
    if (!w) return;
    const today = dateUtil.localDateKey();
    const d = that._store || {};
    d.studyDays = d.studyDays || {};
    d.studyDays[today] = (d.studyDays[today] || 0) + 1;
    d.mastered = d.mastered || {};
    if (known) {
      d.mastered[w.word] = (d.mastered[w.word] || 0) + 1;
    }
    that._store = d;
    that.saveProgress();
    const next = that.data.index + 1;
    if (next >= that.data.total) {
      wx.showToast({ title: '本轮完成！', icon: 'success' });
      that.setData({ todayCount: d.studyDays[today] });
      that.showWord(0);
    } else {
      that.setData({ todayCount: d.studyDays[today] });
      that.showWord(next);
    }
  },

  saveProgress: function () {
    api.putData(this._store).catch(function () {});
  }
});
