const api = require('./api.js');

let audioCtx = null;
let recorder = null;

// 播放 TTS 音频（后端 /api/tts 合成）
function playTTS(text, voice) {
  return new Promise(function (resolve, reject) {
    if (!audioCtx) {
      audioCtx = wx.createInnerAudioContext();
    }
    audioCtx.stop();
    audioCtx.src = api.ttsUrl(text, voice);
    audioCtx.onError(function (e) {
      reject((e && e.errMsg) || '播放失败');
    });
    audioCtx.onEnded(function () {
      resolve();
    });
    audioCtx.play();
  });
}

// 开始录音（返回 stop 后拿到临时文件路径）
function startRecord() {
  if (!recorder) {
    recorder = wx.getRecorderManager();
  }
  return new Promise(function (resolve, reject) {
    recorder.onStop(function (res) {
      resolve(res.tempFilePath);
    });
    recorder.onError(function (e) {
      reject((e && e.errMsg) || '录音失败');
    });
    recorder.start({
      duration: 15000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3'
    });
  });
}

function stopRecord() {
  if (recorder) {
    recorder.stop();
  }
}

// 录音并返回纠音结果（复用后端 /assess -> 讯飞 ISE）
function assess(text, filePath, category) {
  return api.assess(text, filePath, category);
}

module.exports = {
  playTTS: playTTS,
  startRecord: startRecord,
  stopRecord: stopRecord,
  assess: assess
};
