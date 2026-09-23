<template>
  <view class="study-art" aria-hidden="true">
    <view class="art-halo" /><view class="art-orbit" />
    <view class="art-star star-one">✦</view><view class="art-star star-two">✧</view>
    <view class="art-dot dot-one" /><view class="art-dot dot-two" />
    <view class="book-back"><view class="book-spine" /><text>一起探索</text></view>
    <view class="book-pages" />
    <view class="book-front">
      <view class="paper-heading"><view class="paper-heading-line" /><text>01</text></view>
      <text class="paper-title">小小练习家</text>
      <view class="paper-line long" /><view class="paper-line" />
      <view class="paper-answer"><view class="answer-box">✓</view><view class="paper-line" /></view>
      <view class="paper-answer"><view class="answer-box">✓</view><view class="paper-line" /></view>
      <view class="paper-stamp">A+</view>
    </view>
    <view class="art-pencil"><view class="pencil-eraser" /><view class="pencil-body" /><view class="pencil-tip" /></view>
    <view class="math-sticker"><text>×</text><text>÷</text></view>
    <view class="good-sticker">每次进步一点点</view>
  </view>
</template>

<style scoped>
.study-art { position:relative;width:170px;height:192px; }
.art-halo { position:absolute;width:152px;height:152px;right:0;top:22px;border-radius:50%;background:#d6e7d3; }
.art-orbit { position:absolute;width:172px;height:110px;left:-10px;top:42px;border:1px solid #b2c8ac;border-radius:50%;transform:rotate(-34deg); }
.book-back { position:absolute;left:35px;top:29px;width:106px;height:139px;border-radius:5px 12px 12px 5px;background:#458565;transform:rotate(12deg);box-shadow:4px 7px 0 #b8ccb5; }
.book-back text { position:absolute;right:8px;top:9px;font-size:7px;color:#f1eed7;letter-spacing:1px; }
.book-spine { height:100%;width:10px;border-right:1px solid #73a389;background:#30674e;border-radius:5px 0 0 5px; }
.book-pages { position:absolute;left:26px;top:45px;width:102px;height:132px;border:1px solid #cfc8b2;border-radius:5px 9px 9px 5px;background:#e8e2cf;transform:rotate(-9deg); }
.book-front { position:absolute;left:20px;top:36px;width:105px;height:134px;padding:11px 10px;border:1px solid #e6ddc7;border-radius:5px 9px 9px 5px;background:#fffcf3;transform:rotate(-9deg);box-shadow:0 7px 12px #254b3814; }
.paper-heading { display:flex;align-items:center;justify-content:space-between;color:#9e9c87;font-size:7px; }.paper-heading-line { width:21px;height:3px;border-radius:2px;background:#e8b666; }
.paper-title { display:block;margin:7px 0 8px;font-size:11px;font-weight:650;letter-spacing:1px;color:#38664d; }
.paper-line { width:44px;height:3px;margin-top:6px;border-radius:2px;background:#e7e5d8; }.paper-line.long { width:68px; }
.paper-answer { display:flex;align-items:center;gap:7px;margin-top:10px; }.paper-answer .paper-line { margin-top:0; }.answer-box { width:12px;height:12px;border:1px solid #a6c1a3;border-radius:3px;font-size:10px;line-height:10px;text-align:center;color:#4e8260; }
.paper-stamp { position:absolute;right:8px;bottom:10px;color:#cc7961;font-size:22px;font-weight:700;transform:rotate(-9deg); }
.art-pencil { position:absolute;right:16px;top:66px;width:12px;height:103px;transform:rotate(24deg); }.pencil-eraser { height:12px;border-radius:4px 4px 0 0;background:#d98971;border-bottom:4px solid #e9d9b7; }.pencil-body { height:70px;background:linear-gradient(90deg,#d79c43 0%,#f4cc7b 45%,#e9b95a 65%,#d69a3e 100%); }.pencil-tip { width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:17px solid #bca079; }
.math-sticker { position:absolute;right:0;top:19px;display:flex;gap:5px;align-items:center;justify-content:center;width:48px;height:35px;border:3px solid #fff9e9;border-radius:11px;background:#edb18d;color:#8b4c39;font-size:22px;font-weight:600;transform:rotate(13deg);box-shadow:0 3px 0 #ad967329; }
.good-sticker { position:absolute;left:9px;bottom:7px;padding:4px 10px;border:2px solid #fff8e9;border-radius:7px;background:#efd583;color:#765c2c;font-size:9px;transform:rotate(-7deg); }
.art-star { position:absolute;color:#c69340;line-height:1; }.star-one { left:0;top:13px;font-size:24px; }.star-two { right:0;bottom:13px;font-size:25px;color:#6c9b75; }.art-dot { position:absolute;width:5px;height:5px;border-radius:50%; }.dot-one { left:3px;top:82px;background:#c98368; }.dot-two { right:37px;top:0;background:#a4bd86; }
</style>
