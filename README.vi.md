[![SEASON UPGRADE 25, 26](docs/season-upgrade-25-26.svg)](https://www.mediafire.com/file/7yteho45esxfnu8/FO3ID-Season-25-26-LIVE-client.rar/file)

# FO3ID Private Server

[English](README.md) | [Bahasa Indonesia](README.id.md) | [简体中文](README.zh-CN.md) | [ไทย](README.th.md) | **Tiếng Việt** | [한국어](README.ko.md)

> Bản dịch của [README.md](README.md). Nếu có chỗ khác nhau, README.md là bản mới nhất.

**Mới:** thẻ 25 LIVE và 26 LIVE của FIFA Online 4 thành hai mùa mới (chỉ số tính là +0, đặc tính và biểu tượng mùa của FO4), 26 LIVE là mùa mặc định. Xem `tools/fo4_season.py`.

Máy chủ riêng chạy cục bộ cho **FIFA Online 3 Indonesia** (Garena, client build 654420), viết bằng
Python. Garena đã đóng máy chủ chính thức ngày 2020-06-30; dự án này dựng lại phần backend mà client
kết nối tới, để có thể chơi game offline trên một máy tính.

> Không liên quan đến EA, Spearhead hay Garena. Kho mã này **không chứa file game nào** (không có
> client, cơ sở dữ liệu, tài nguyên hay nhạc); bạn cần tự cài FO3 ID. Dự án **không** kèm theo, không
> sửa đổi và không vượt qua hệ thống chống gian lận của client (XIGNCODE3 / HackShield); việc đó nằm
> ngoài phạm vi. Làm ra để bảo tồn game và nghiên cứu.

Giao diện game là tiếng Indonesia. Các tên như Liga, Cup, Market, Tukar, Tim inti, Tim Cadangan,
Item saya, Gudang bên dưới là tên màn hình trong game, được giữ nguyên để dễ tìm trong game.

## Những gì đã chạy được

Đã thử trong client thật (giao diện tiếng Indonesia):

- Đăng nhập → chọn / tạo HLV (chọn CLB trong 501 CLB có bản quyền) → sảnh (FREEROAM).
- **Single → Liga** (cả mùa giải: lịch thi đấu, trận đấu, bảng xếp hạng, phần thưởng, thăng hạng) và
  **Cup** (bốc thăm, vòng bảng, loại trực tiếp, hiệp phụ, luân lưu).
- **Market** (mua / bán; giá thẻ theo chỉ số và cấp thẻ: trung vị giá trên fifaaddict của mọi thẻ cùng
  chỉ số), **Upgrade** (cấp +1…+10), giao dịch cầu thủ **Tukar** và **Tukar Scout** (mọi thẻ trên
  Market, không chỉ thẻ có bản quyền trong khu vực), Tim inti (đội chính) / Tim Cadangan (đội dự bị),
  lưu đội hình và chiến thuật.
- **Shop** (Cửa hàng) đủ mọi tab (gói cầu thủ, vật phẩm tiêu hao, gói quà, MP Shop, gói tháng và gói
  nối tiếp, thưởng đặc biệt), mở gói với cấp thẻ ngẫu nhiên, Item saya (vật phẩm của tôi), Bag (hộp quà),
  quà đăng nhập hằng ngày. **Gudang** (Item saya > Gudang, kho): chuyển gói và vật phẩm tiêu hao vào và
  lấy ra. Gói thêm: **All Season +8** (mùa bất kỳ, +1…+8) và một gói cho '07 cùng mỗi mùa có trên
  fifaaddict.
- Luôn có VIP + ưu đãi phòng máy chính thức (IGR), xóa / khôi phục HLV, thẻ mùa '17.
- Danh sách sơ đồ (sơ đồ riêng của CLB + 33 sơ đồ phổ biến của game, đọc từ bảng sơ đồ của client) và
  cấp HLV / cầu thủ: EXP sau mỗi trận, cầu thủ LV.1-23 (+1 mọi chỉ số mỗi cấp), HLV LV.1-100.
- Âm thanh game và nhạc menu EA Trax. `tools/eatrax_song.py` đặt bài hát của bạn lên đầu, nhưng sau đó
  game bị crash sau mỗi trận (xem lỗi đã biết bên dưới).
- Trang quản trị web tại http://127.0.0.1:8088/ (EP, cầu thủ, gói, quà, quà hằng ngày, thưởng sau trận, cài đặt trận, kinh tế, chat AI, Cửa hàng, nhật ký)
  có chọn ngôn ngữ (issue #15): Bahasa Indonesia, English, 简体中文, ไทย, Tiếng Việt, 한국어; trình duyệt
  nhớ lựa chọn.
- Áo đấu CLB thật trong trận (kit id = `teamid << 5 | type`; kiểu cũ `<< 10` hiện thành ô bàn cờ).
- Trận đấu chơi hết hiệp hai khi bật **team color** (thưởng đội hình) (trước đây thưởng theo mùa làm crash
  lúc nghỉ giữa hiệp), rồi hiện màn hình EXP và phần thưởng.

Đã thêm và qua kiểm thử, nhưng chưa kiểm tra trong client:

- Bản thân phần thưởng **team color**: 11 cầu thủ đá chính được cộng OVR khi cùng CLB (4-5 người +1, tối
  đa 10-11 người +4), cùng quốc gia hoặc cùng mùa (5-6 người +1, tối đa 9-11 người +3); mỗi cầu thủ chỉ
  tính mức tốt nhất.
- **Opsi > Kontrol** (phím bàn phím và tay cầm) được lưu: máy chủ luôn gửi bố cục phím mặc định của game,
  nên màn hình đó áp dụng và lưu được thay đổi (trước đây thay đổi bị mất).
- **Chọn áo đấu** ở màn hình cài đặt trận (sân nhà / sân khách mỗi bên) được dùng trong trận.
- **Màn hình chọn HLV** hiện cầu thủ đắt giá nhất của CLB trong áo của CLB (trước đây hiện cầu thủ
  Barcelona mặc định của game).
- Sửa crash: popup thông báo lúc khởi động (URL web trống), hướng dẫn giải đấu Beginner's Guide (thiếu
  script).
- **Tỉ lệ nâng cấp**: tỉ lệ cơ bản theo cấp đích, nhân với nhãn "Rasio bonus keberhasilan" mà tab Upgrade
  hiện theo cấp của thẻ nguyên liệu (Kosong x1, Low x1.1, Normal x1.25, High x1.5). Nâng cấp thất bại từ
  +5 trở lên bị tụt một cấp.
- **Gói Top 200**: các gói thêm giờ cho 200 thẻ tốt nhất của mùa đó ("17 Top 200", "07 Top 200", …);
  **All Season Top 300 +8** cho thẻ mùa bất kỳ có chỉ số từ 81 trở lên.
- **Nâng cấp bằng thẻ +0** (issue #5): thẻ +0 của chính CLB giữ cấp thẻ đích ở 100% (+4 dùng +0 vẫn là +4)
  và thẻ +10 cũng dùng được; thẻ được giữ lại rời Tim Cadangan khi nó thế chỗ trong đội hình của thẻ bị dùng.
- **Upgrade 2.5** (màn hình Upgrade mới hơn của client, `features...enhancement.v2_5`):
  - **điểm nâng cấp**: nâng cấp thất bại cho điểm; "Gunakan poin" dùng điểm để được +10%; mua thêm miễn phí
    ở Shop > Paket (Upgrade Point 100 / 500 / 1.000);
  - **vật phẩm tăng tỉ lệ** Enhancement Boost Gold / Silver / Bronze (+15 / +10 / +5%), miễn phí ở
    Shop > Dapat dikonsumsi;
  - **sự kiện nâng cấp** vĩnh viễn (+10% cho cấp đích +1…+9, `GET /events`);
  - "Coba pengembalian lagi" lấy lại cấp bị mất do thất bại, bằng điểm.
- **Tukar v2** (`trade2`): giao dịch được đánh giá theo giá trị (TP) qua 15 mức, mỗi mức có cấp đề nghị tối
  đa; tab hiện HLV khác "hôm qua" nhận được gì ở mức đó; thẻ mùa huyền thoại tính 1.5 lần; không giới hạn
  theo ngày hay giá trị. Tukar Scout vẫn dùng song song.
- **Tukar Scout**: hai tuyển trạch viên khác của client, Scout Khusus (sự kiện; nhiệm vụ mùa huyền thoại) và
  VVIP Scout (đề nghị tốt nhất; nhiệm vụ 1 tỉ EP). Bỏ Scout Amatir để danh sách vừa 5 dòng (trước đây khi
  danh sách cuộn được, nhiệm vụ hoàn thành lại sáng thẻ của tuyển trạch viên khác hoặc không sáng gì).
- **Thưởng đội hình theo cấp nâng** ("Upgraded Team" trong client): cầu thủ đá chính cấp +2, +5 hoặc +8 trở
  lên; 5-6 / 7-8 / 9-11 người cho +1 / +2 / +3, +2 / +3 / +4 và +3 / +4 / +5 OVR. Loại một cấp ("+3 club" …
  "+10 Golden summit") cần cả 11 người đá chính ở cấp đó hoặc cao hơn: +4 (club +3/+4), +5 (silver +5…+7),
  +6 (Golden passion +8/+9), +7 (Golden summit +10). Cầu thủ nhận thưởng cấp nâng tốt nhất cộng thêm vào
  thưởng CLB / quốc gia / mùa tốt nhất.
- **Mọi team color có tên trong client** (hiện có 188):
  - 27 CLB (Real Madrid … Jeonbuk): các mức của Single team cộng thưởng riêng của CLB lấy từ tooltip trong
    game, vd. Barcelona MF agility +3;
  - 30 quốc gia: các mức của Satu Negara cộng vd. Spanyol MF ball control +2;
  - thưởng theo mùa với tên trong game (World Best tối đa +5, World Legend, 2014 WC All-Star, …);
  - khoảng 75 loại đặc biệt: '14 WC và EC từng quốc gia, nation BEST, MSN / BBC Trio, Arsenal
    Invincibles, Galácticos, LEGENDS, TOP 100, Power Header, New Star, ….

  Chỉ số thưởng và danh sách cầu thủ gốc là dữ liệu máy chủ và đã mất. Danh sách cầu thủ lấy từ cơ sở dữ
  liệu cầu thủ (mùa, CLB, cầu thủ được nêu tên, giới hạn chỉ số); chỉ số thưởng lấy từ dòng tooltip duy nhất
  game còn giữ. Không đưa vào: loại [Test], "+2~7", "14 WC Single Nation" và bốn mục CLB trùng lặp.
- **Formasi** (sơ đồ) không còn mở ra với "Tidak cukup pemain" (không đủ cầu thủ) (màn hình này tải đội hình
  mẫu 1, thứ máy chủ chưa từng gửi). Chỗ trống trong đội hình chính (issue #7, nâng cấp hai thẻ đá chính
  của cùng một cầu thủ) được lấp từ ghế dự bị, và ghế dự bị không bao giờ có thẻ thứ hai của cùng một cầu
  thủ. Mỗi cầu thủ đá chính nhận dữ liệu `starting` (workrate và vị trí trên sân): thiếu nó game hiện cầu
  thủ đó ở ghế dự bị.
- **Tim > Peran** lưu đội trưởng và từng người đá phạt (issue #8: thiếu `PUT /game/my/team/captain` và
  `/game/my/team/kickers/<0-4>`). Năm vị trí đá phạt (phạt góc trái, phạt góc phải, đá phạt, phạt đền,
  đá phạt 2) giữ nguyên chỗ; vị trí trống lấy một cầu thủ đá chính.
- **Tim > Locker room** (phòng thay đồ) chạy được (issue #13): kiểu áo và tay áo, hình xăm, băng cổ tay,
  găng tay (thủ môn: 39 mẫu găng), tất, bó gối, 614 đôi giày theo hãng, và số áo (chọn số đã có người mặc
  sẽ đổi với người đó). Trước đây thiếu bảng vật phẩm `/static/db/LOCKERROOMITEM`, nên mọi danh sách đều
  trống và bảng giày bị lỗi. Diện mạo cầu thủ được lưu trên thẻ, và Item saya có một vé phòng thay đồ vĩnh
  viễn, thứ game cần để hiện diện mạo đó trong trận. Băng cổ tay, găng tay và bó gối chỉ có mẫu sẵn của
  client (mỗi loại một).
- **Quản lý Cửa hàng trên trang quản trị** (issue #10): mọi tab Cửa hàng (gói cầu thủ, vật phẩm tiêu hao,
  gói quà, gói tháng, Đề xuất, MP Shop, Thưởng đặc biệt, gói nối tiếp). Tạo gói mới (theo mùa, top N, OVR,
  cấp tối đa, vị trí, giải đấu), hộp ngẫu nhiên, thẻ EP, gói quà và gói tháng, với bất kỳ biểu tượng nào
  trong 147 biểu tượng cửa hàng của client. Sản phẩm có sẵn có thể sửa, ẩn hoặc đặt giá cố định, và cả
  Cửa hàng có thể miễn phí hoặc không. Thay đổi lưu vào `gamedata/shop.json`.
- Phiếu **Simulasi Liga** (mô phỏng giải đấu) (vật phẩm 2001, Shop > Dapat dikonsumsi): nút Simulasi của
  Liga cho kết quả trận mà không cần chơi, mỗi trận một phiếu. Màn hình mô phỏng phát lại bàn thắng, cú sút,
  pha cứu thua và thẻ phạt khớp với kết quả (trước đây `eventlist` trống nên hiện 0-0), và màn hình kết quả
  sau đó hiện tỉ số, điểm và thống kê cầu thủ, tỉ lệ kiểm soát bóng và MOTM (trước đây trống), rồi phần
  thưởng EP và quay lại menu Liga. Nút này đếm số phiếu trong Item saya và từng bị tắt vì chưa có vật phẩm.
  Có thể tạo phiếu mới trên trang quản trị (loại "Phiếu Mô phỏng giải đấu").
- **Màn hình đội hình trước trận** (Liga và Cup, issue #16): đổi chỗ, thay người và đổi sơ đồ giờ được
  giữ và lưu vào CLB (`PUT /match/<id>/side/<side>/squad` chưa có xử lý, nên mỗi thay đổi tự hoàn tác).
  Danh sách sơ đồ đã có dữ liệu, và thanh thể lực hiện đầy (không giữ độ mệt giữa các trận).
- **Chỉ số FW / MF / DF của đội khớp với cầu thủ** (issue #18): ở màn hình đội hình và sảnh, đó là trung bình
  chỉ số mà danh sách cầu thủ hiển thị (chỉ số ở vị trí của cầu thủ cộng cấp nâng cấp, level và team color).
  Trước đây tính từ chỉ số thẻ gốc, thấp hơn khoảng 12.
  Trước trận (Giải đấu, Cúp, Rank) danh sách cầu thủ không tính team color, nên các thanh chỉ số ở đó cũng
  không tính; phần thưởng vẫn có hiệu lực trong trận.
- **Các tab Rekor liga** (issue #19): bảng xếp hạng đã hiện (tab bị lỗi vì thiếu bảng `league2difficulty`, bảng này
  giờ cũng quyết định đội lên hạng hay xuống hạng cuối mùa). Rekorku liệt kê số trận, điểm, bàn thắng, kiến tạo,
  đường chuyền, tắc bóng và cứu thua của từng cầu thủ trong các trận đã đá của mùa, còn Rekor gabungan hiện đội hình
  tiêu biểu và những người dẫn đầu thống kê của mùa. Chỉ tính cầu thủ của mình, và trận mô phỏng không cộng thống kê cầu thủ.
- **Squad A / B / C trong Formasi** (issue #20): ô bên trái nút đội hình chọn một trong ba đội hình đã lưu
  (trước đây trống vì máy chủ không gửi số đội hình). Mỗi đội hình giữ đội chính, sơ đồ và vai trò riêng.
- **Cài đặt tay cầm và camera được giữ trong trận** (issue #21): sau Opsi > Konfirmasi, game đọc lại tùy chọn
  đã lưu từ phản hồi của máy chủ, trước đây không có, nên mỗi trận lại quay về tùy chọn lúc đăng nhập (bàn phím,
  camera cũ). Trong trận, F3-F9 đổi camera (F5 = Co-op).
- **Ganti tim (đổi đội) hiện câu lạc bộ và cầu thủ của bạn** (issue #23): màn hình câu lạc bộ của vật phẩm này
  giờ hiện giải đấu, đối thủ derby, sân nhà, năm xây và sức chứa, cùng cầu thủ của bạn trong áo đấu của câu lạc bộ
  mới với ngày sinh, chiều cao và cân nặng. Trước đây thông tin câu lạc bộ từ máy chủ không có những thứ này, và
  không có áo đấu thì cầu thủ 3D không bao giờ được vẽ.
- **Chỉnh được độ cao và zoom camera** (issue #24): trong Opsi > Kamera setting, các thanh Customise (độ cao
  và zoom; với camera Pro là zoom, tốc độ và độ lắc) trước đây không có giá trị và không chỉnh được,
  vì máy chủ gửi thiết lập camera rỗng. Giờ chúng bắt đầu ở 10 (trên 20).
- **Có đủ đội tuyển quốc gia trong Tim lain** (issue #24): giải International (quốc gia cuối cùng
  trong danh sách) có 40 đội tuyển, trong đó có Ý, Anh, Đức, Tây Ban Nha và Pháp. Đội hình đội tuyển
  lấy từ liên kết đội tuyển của từng cầu thủ; trước đây chỉ có các đội mà cầu thủ không thuộc câu lạc
  bộ có bản quyền.
- **Vị trí cầu thủ trên màn hình kết quả** (issue #26): sau trận, sân trên màn hình kết quả xếp chồng
  mọi cầu thủ ở khung thành vì game báo mọi cầu thủ là thủ môn. Giờ máy chủ gán cho mỗi cầu thủ vị
  trí theo ô của họ trong đội hình.
- **Thẻ thưởng sau trận** (issue #26): các thẻ trên màn hình thưởng trước đây trống. Giờ có ba thẻ:
  thẻ bạn chọn cho EP (1.000 đến 10.000), gói cầu thủ (Semua Pemain hoặc '14 Top 200) hoặc vật phẩm
  Lucky EP, hai thẻ còn lại cho thấy phần thưởng có thể nhận.
- **Gói draft và viên EXP** (issue #27): Shop > Pak pemain bán gói draft ("06 Draft Pick 3",
  "2017 Draft Pick 5", "World Legend Draft Pick 3"). "Gunakan" mở màn hình chọn cầu thủ, điền sẵn các thẻ
  giá trị nhất của mùa đó; chọn N thẻ của mùa đó (tìm theo tên, giải đấu hoặc câu lạc bộ) rồi một thẻ trong
  số đó được mở. Shop > Dapat dikonsumsi bán viên EXP (1.000, 5.000, Max = LV.23, một viên cho LV.10 trở
  xuống, một viên cho thẻ 2017): chọn một cầu thủ và anh ấy nhận EXP đó. Trước đây thiếu các yêu cầu của
  màn hình draft (`/item/draftpack/<id>/players/<n>`, `/transfer/price/default/<grade>`) và loại vật phẩm
  viên EXP. Trang admin tạo thêm được cả hai (ô "Draft" của gói, loại vật phẩm "EXP Capsule").
- **Multiple > Rank: các HLV khác và trận đấu thật** (issue #30): màn hình xếp hạng trước đây dừng ở lỗi UI
  vì máy chủ không gửi hạng đấu, phần thưởng và thành tích ladder. Giờ màn hình mở được, và các HLV ảo lấp
  đầy bảng xếp hạng: top 3 (VS Manager Top) và xếp hạng bạn bè gồm 20 người, mỗi người có tên, câu lạc bộ,
  hạng đấu và thành tích thay đổi dần trong ngày khi họ thi đấu. Lúc đầu có 100 HLV, thêm 850 người khác, rồi mỗi
  ngày thêm 0-3 người mới, tối đa 1.000. Mỗi người đá theo lối chơi riêng (kiểm soát bóng, phản công, pressing tầm cao, bóng dài,
  dựng xe buýt hoặc tấn công tổng lực: sơ đồ, chiến thuật và cách chạy chỗ) trong bộ áo của câu lạc bộ mình,
  với thẻ ngẫu nhiên từ mọi câu lạc bộ và mùa giải quanh rating của họ, mỗi thẻ có cấp thẻ riêng (từ +1 với
  người mới đến +6 trở lên) và level riêng. Ngày qua ngày, họ mua bán thẻ, nâng cấp thẻ (nâng cấp thất bại
  từ +5 bị tụt một cấp) và tăng level cho thẻ. Rank 1 on 1 và VS Manager đá một trận thật với một trong năm
  HLV có rating gần bạn nhất: màn hình đội hình, cài đặt trận, rồi cả trận với AI của game điều khiển phía
  đối thủ, sau đó là kết quả, phần thưởng và rating xếp hạng mới của bạn, hiện trong các bảng của màn hình
  Rank, trong cửa sổ thành tích (các trận gần nhất, biểu đồ mùa giải) và trong danh sách trận đấu của
  Info Manager. Trong trận, đối thủ chat trong khung chat của trận theo tính cách riêng (lúc giao bóng, khi
  có bàn thắng của hai bên, sút trượt, cứu thua, và trả lời khi bạn gõ chat), rồi bình luận về kết quả khi
  quay lại màn hình Rank; tab Chat AI trên trang quản trị dùng để tắt hoặc chọn ngôn ngữ (Indonesia, Anh,
  Việt). Messenger giờ mở được (trước đây nó chờ một danh sách thông báo mà máy chủ không bao giờ gửi) và
  hiện 20 người bạn ở trạng thái online, bận (đang trong trận Rank) hoặc offline theo khung giờ chơi của họ
  (08:00-02:00 WIB); nút Info của một người bạn hiện hồ sơ và đội hình của người đó.
- **Market sôi động** (issue #30): các HLV ảo mua thẻ bạn đăng bán ("Dijual" tự chuyển thành "Terjual" trong
  vài phút, nhanh hơn khi giá rẻ hơn, kèm thông báo nổi "terjual seharga" và một thông báo ghi tên người
  mua; Batal và Ulang dùng được) và tự đăng bán thẻ của mình bên cạnh lượng thẻ +1..+3 có sẵn, cả ở các cấp
  thẻ khác, với giá thấp hơn giá thị trường một chút, còn Kuantitas thay đổi mỗi giờ. Tab Market Price trong
  cửa sổ thẻ vẽ biểu đồ giá của 30 ngày gần nhất.
- **Cài đặt kinh tế** (issue #30): tab Ekonomi (Kinh tế) mới trên trang quản trị cho bạn chỉnh độ khó của
  game tùy ý: hệ số nhân giá cầu thủ và giá gói, EP ban đầu của HLV mới, tùy chọn Shop miễn phí và Market
  biến động. Với Market biến động, giá mỗi cầu thủ lên xuống theo từng ngày (tăng hoặc giảm tối đa khoảng
  13%), thỉnh thoảng HLV ảo đăng bán thẻ giá hời, và bạn có thể đặt giá bán đến 105% giá thị trường (nhưng
  lâu có người mua hơn), nên mua rẻ bán đắt sẽ có lãi. Các mẫu có sẵn: Dễ (như trước: Shop miễn phí, giá cố
  định), Thực tế (Shop tính phí theo giá trị các thẻ trong gói, Market biến động, 300.000 EP ban đầu) và Khó
  (giá x2, 100.000 EP). EP nhận sau mỗi trận vẫn được chỉnh ở tab Thưởng sau trận.
  Khi Shop tính phí, không có cách nào tạo EP từ hư không: phí Nâng cấp bằng giá trị trung bình nó thêm vào
  (khôi phục trả bằng EP), đề nghị của Tukar và Scout không vượt quá giá trị các thẻ đã đưa, phiếu Mô phỏng
  giải đấu có giá bằng phần thưởng của một vòng, và với Market biến động, giá gói bằng giá trị các thẻ lúc
  đắt nhất (+13%), vì gói có thể để dành mở vào bất kỳ ngày nào.
  Vật phẩm không chứa EP (tăng tỉ lệ nâng cấp, điểm nâng cấp, viên EXP, đổi tên hoặc đổi đội) có giá cơ bản
  nhân hệ số giá cầu thủ, nên ở mức Khó giá gấp đôi.
  Thay đổi có hiệu lực ngay cả khi game đang chạy: máy chủ báo game bỏ danh sách Shop nó giữ suốt phiên, nên
  tab Shop hiện giá mới ở lần mở tiếp theo; tab nào đã mở kể từ lúc khởi động game thì vẫn giữ giá cũ cho đến
  khi khởi động lại game. Việc kiểm tra hàng giới hạn của Shop không còn báo "Kesalahan UI telah terjadi".
- **AI Chat nhiều gấp mười lần** (issue #30): HLV ảo có 20 câu cho mỗi tình huống và mỗi tính cách ở mỗi ngôn
  ngữ, tổng cộng 2.700 câu: chào hỏi và chuyện bóng đá lúc giao bóng, phản ứng khi ghi bàn, sút hỏng và cứu
  thua, trêu đùa khi bạn gõ chat, và nhận xét về kết quả. Không câu nào chứa từ mà bộ lọc chat của game sẽ che
  (bộ lọc còn che cả từ nằm bên trong từ dài hơn).
- **HLV ảo xây đội hình theo cách riêng** (issue #30): mỗi người có một chủ đề đội hình cố định: thẻ bất kỳ
  gần rating của họ; một CLB hàng đầu (Real Madrid, Barcelona, Atletico, hai đội Manchester, Chelsea,
  Liverpool, Arsenal, Tottenham, Bayern, Dortmund, Juventus, Milan, Inter, Roma, Napoli, PSG) với cầu thủ
  hiện tại hoặc từng khoác áo; một đội tuyển hàng đầu (Brazil, Argentina, Tây Ban Nha, Đức, Pháp, Anh, Ý,
  Hà Lan, Bồ Đào Nha, Bỉ, Uruguay, Croatia); một team color của game (một mùa thẻ hoặc một bộ có tên); một
  ngôi sao cùng đồng đội CLB hoặc đồng hương; meta; hoặc một chỉ số (tốc độ, thể lực, kỹ thuật, chuyền,
  phòng ngự, dứt điểm, cầu thủ trẻ, cầu thủ thế hệ cũ). HLV càng mạnh càng hay theo meta và team color.
  Chủ đề chỉ lấy thẻ gần rating của họ nên đội hình không mạnh hơn vì nó.
- **Cài đặt trước trận** (issue #31): các nút chọn trên màn hình cài đặt trận của Multiple > Rank đã dùng
  được cho sân (70 sân có đủ dữ liệu trong client), thời gian trong ngày (ban ngày hoặc ban đêm), thời
  tiết (quang đãng, mưa, tuyết, âm u: thành hoàng hôn nếu là ban đêm), thời lượng trận (6, 8, 10 hoặc 12
  phút) và quả bóng (9 loại bóng). Lựa chọn gần nhất được giữ cho các trận tiếp theo, kể cả Liga và Cup;
  màn hình trước trận của hai chế độ này chỉ hiện các giá trị, nên tab Cài đặt trận mới trên trang quản
  trị cũng chỉnh được chúng, và còn chọn được "sân của đội chủ nhà" hoặc "ngẫu nhiên". Máy chủ sửa hai
  nhãn trong chuỗi tiếng Indonesia của client: ban ngày từng ghi là "Waktu" (thời gian), âm u là "Malam"
  (đêm); màn hình của Liga/Cup vẫn gọi âm u là "Salju" (tuyết).
- **Bàn phím và tay cầm giữ preset điều khiển riêng** (issue #32): Opsi > Kontrol chỉ lưu một preset, cho
  thiết bị đang dùng, và đưa thiết bị còn lại về preset đầu tiên khi bạn chuyển thiết bị. Giờ đây máy chủ
  nhớ preset dùng gần nhất của từng thiết bị và khôi phục nó sau khi bấm Konfirmasi (màn hình hiện preset
  đó ở lần mở tiếp theo; trận đấu dùng nó ngay từ lúc giao bóng).
  Để màn hình hiện ngay preset của thiết bị khi chuyển, hãy đóng game rồi chạy một lần
  `python tools/control_presets.py`: công cụ này vá màn hình Kontrol của client (có lưu bản sao lưu;
  `--remove` khôi phục bản gốc).
- **Menu Manager đã có dữ liệu** (issue #33): Info Manager hiện thành tích của bạn thay vì "-": số trận, bàn
  thắng, số trận thắng và chuỗi thắng ở Giải đấu, Cúp và Rank, các chức vô địch giải và mức độ đã đạt, số cúp đã
  thắng cùng tiền thưởng, số thẻ đã mua và bán cùng thẻ đắt nhất của mỗi loại, thời gian chơi, phần giới thiệu và
  ảnh của bạn. Các số liệu được tính từ phiên bản này. Manager Ranking hiện giá trị đội của bạn trong 30 ngày qua
  so với mức trung bình của 20 người bạn, thứ hạng của bạn trong nhóm đó và thay đổi thứ hạng so với hôm qua.
- **Nhiệm vụ và thành tích** (issue #33): Manager > Daftar pencapaian có các dòng huy hiệu (cấp HLV, số trận,
  số trận thắng, nâng cấp, cấp thẻ cao nhất, giá trị đội, bàn thắng, thắng Rank), mỗi thành tích có 5 cấp thưởng
  EP, gói và vật phẩm để nhận, và đeo được huy hiệu khi xong cả dòng; thêm một dòng nhiệm vụ hằng ngày (chơi,
  thắng, ghi bàn, chơi Rank) làm mới lúc 00:00 WIB. Nút Quest trên thanh trên cùng mở nhiệm vụ hằng tuần (làm
  mới thứ Hai lúc 00:00 WIB) kèm đồng hồ đếm ngược; nhiệm vụ hoàn thành thưởng GP để đổi các hộp
  quà trong cửa sổ đó (EP, Lucky EP, gói, tăng tỉ lệ nâng cấp, Kotak Emas). Máy chủ đếm các trận bạn chơi và các
  lần nâng cấp thành công. Tab Misi mới trên trang quản trị dùng để bật hoặc tắt, chọn ngôn ngữ (tiếng Indonesia,
  tiếng Anh, tiếng Việt) và hệ số mục tiêu, phần thưởng; thưởng EP cũng theo giá cầu thủ ở tab Kinh tế.
- **Trọng tài lúc giao bóng** (issue #33): hai trợ lý trọng tài được tạo từ một bản ghi trống (không có trọng tài
  đó trong danh sách của game), với đầu, tóc và thân không có tệp tài nguyên, nên trông méo mó khi xếp hàng ra sân.
  Giờ máy chủ dùng các trọng tài có thật trong game.
- **Bình luận tiếng Việt từ client FO3 VN** (issue #34): khi đã tắt game, chạy
  `python tools/commentary.py "<thư mục client FO3 VN>"`. Script chép `audiodata\speechdata\vie_vn` của client
  VN vào cạnh phần bình luận tiếng Anh của client này (`eng_us`) và chỉ để tiếng Việt làm ngôn ngữ bình luận
  trong `data\loc\locale.big` (có lưu bản sao lưu); sau đó game đọc bình luận từ `vie_vn`. `--remove` trả lại
  bình luận tiếng Anh.
- **Thưởng lên cấp HLV** (issue #35): mỗi cấp HLV từ 2 đến 100 nhận phần thưởng lên cấp của FO3 (bảng trên
  fifaaddict): EP cùng vật phẩm như gói Top 300, Top 100 và Best, gói giải đấu 65+ và GK 65+, phiếu mô phỏng giải
  đấu, phiếu đổi đội và EXP capsule. Phần thưởng vào Bag ("Hadiah naik level Lv.N"); màn hình sau trận hiện chúng
  trong cửa sổ lên cấp, và biểu tượng thông tin liệt kê phần thưởng các cấp tiếp theo. Vật phẩm FO3 mà máy chủ
  không dùng (gói staff, Red Ball, phiếu phòng thay đồ và tăng thưởng, chuyển EXP) bị bỏ qua. Thưởng EP theo giá cầu
  thủ ở tab Kinh tế.
- **Staff** (Tim > Manajemen Staff): hệ thống staff của FO3 hoạt động trở lại. *Rekrut* (tuyển): gói staff
  bằng EP (Basic FW / MF / DF / GK / ALL, Pro, Premium, Giám đốc kỹ thuật, Premium Medical) và mỗi ngày một
  gói ALL miễn phí khi đăng nhập, thêm một gói khi chơi đủ 3 trận. *Staff yang dimiliki* (staff đang có): 7 ô
  vai trò (FW, MF, DF, HLV trưởng, GK, HLV thể lực, Giám đốc kỹ thuật); staff ở đúng ô tăng chỉ số cho các cầu
  thủ đá chính thuộc nhóm vị trí đó (HLV thể lực, HLV trưởng và Giám đốc kỹ thuật: mọi cầu thủ đá chính) trong
  danh sách đội hình và trong trận, với hợp đồng 50 trận gia hạn bằng EP. *Latihan* (huấn luyện): dùng staff
  khác để nâng cấp (0.5 đến 5 sao) và tăng chỉ số cho một staff. *Pembinaan* (tu nghiệp): gửi staff ra nước
  ngoài 5-10 trận để đổi hoặc tăng một chỉ số. Tên và chỉ số tăng theo danh sách fo3staff của fifaaddict; cấp,
  giá và hợp đồng do máy chủ tự đặt (số liệu của Garena đã mất), và giá EP theo giá cầu thủ ở tab Kinh tế.
  Client chỉ có ảnh của 7 staff; `python -I tools/fa_faces.py --staffs` thêm ảnh còn lại từ fifaaddict.
  Quản lý ảo thi đấu với team color của họ như bạn, và có staff theo cấp (thêm một ô vai trò mỗi 12
  cấp).
- **Mở được hộp ngẫu nhiên** (Kotak Platinum và các hộp khác, issue #12): màn hình hộp liệt kê phần thưởng
  từ `staticdata.availables`, trước đây bị thiếu, nên mọi hộp đều lỗi khi bấm "Gunakan" (dùng).
- **Thẻ mới vào Tim Cadangan**: thẻ từ gói, giao dịch, Market, Bag hoặc trang quản trị hiện "-" ở cột Tim
  trong Skuad, sẵn sàng cho Tukar Scout. Nút của thẻ chuyển nó sang Tim inti (RES màu xanh: Tim inti nằm
  ngoài 18 cầu thủ của đội hình), nơi chứa được cả CLB (200). Trang quản trị có thể chuyển mọi thẻ Tim
  Cadangan sang Tim inti cùng lúc.
- **Tìm kiếm trên Market** thấy thẻ của mọi mùa: game chỉ tìm các mùa trong `/static/roster`, vốn thiếu 29
  mùa có thẻ trên Market (World Legend, World Best, '14 TOTS, …), nên vd. WL R. Gullit không bao giờ hiện
  ra. Danh sách mùa trong bộ lọc Market đã dùng được (issue #14: chọn mùa báo lỗi "cannot convert 39 to
  Array", vì `value` của mỗi mùa phải là danh sách) và hiện tên mùa của client (World Legend, 02 Chinese
  Legend, …). Kết quả tìm kiếm không còn hiện các thẻ engine mà các CLB AI ở Liga và Cup dùng để thi đấu
  (mang biểu tượng mùa '17, chỉ số tới 127, vd. L. Messi 125; vốn cũng không mua được): mùa 0 của các thẻ
  này đã được bỏ khỏi `/static/roster`, và mục "default" ở đó giờ là mùa '17 của chính client (88), nên
  "2017" chỉ còn hiện một lần trong danh sách mùa.
- **Mọi thẻ giao dịch được** đều có trên Market, trong giao dịch và trong gói: một thẻ được tính khi
  fifaaddict có nó hoặc chính game đánh dấu nó giao dịch được (`permid.transferable`). Chỉ dùng fifaaddict
  sẽ thiếu 6.599 thẻ (4.313 thẻ trong đó là '17); Market giờ có 44.703 thẻ. Gói mới **Semua Pemain** (tất
  cả cầu thủ) có thể cho bất kỳ thẻ nào trong số đó.
- **Tim > Klub > Informasi tim** (issue #9) hiện ngày thành lập, sân nhà và "năm xây / sức chứa"
  (`coach.career`, `coach.stadium`, `GET /stadium/<id>` từ bảng sân của client), và bảng cầu thủ (nút
  chuyển, cầu thủ 3D, giá, cấp thẻ), vốn trống khi không có sân. Tên trong cơ sở dữ liệu của client được
  đọc theo UTF-8 (`tools/re/eadb.py` trước đây đọc latin-1).
- **Hiệu ứng sáng khi mở gói** theo giá trị thẻ: không có dưới 10 triệu EP, rồi mức 1-3 từ 10 triệu, 100 triệu
  và 1 tỉ EP.

Lỗi đã biết, chưa giải quyết: khi cài bài hát EA Trax riêng bằng `tools/eatrax_song.py`, game cạn vùng nhớ
RAssets sau mỗi trận, lúc màn hình Cup hoặc sảnh tải lại (crash tại
`FifaRNA::Crowd::PlacementData::Seats[]`); với nhạc gốc của game thì không. Crash y hệt khi bài hát ở dạng PCM
thô (37,7 MB), dạng EALayer3 (6,5 MB, `tools/re/ealayer3.py`) thêm làm bài thứ 10, và dạng EALayer3 thay
TrackID 1 với kho nhạc nhỏ hơn bản gốc, nên kích thước nhạc không phải nguyên nhân. Hãy dùng nhạc gốc của
game: `python -I tools/eatrax_song.py --restore` khôi phục lại.

Chưa làm: chơi online với người khác (xếp hạng PvP, giao hữu, King of the Hill), Road to World, mô phỏng giải đấu.

## Yêu cầu

- Windows, Python 3.12, `pip install cryptography` (cho messenger + trích xuất cơ sở dữ liệu).
- Client FO3 ID đã cài (đường dẫn mặc định `D:\FO3ID\32795`; nếu ở chỗ khác, đặt `FO3_GAME` là thư mục
  đó; máy chủ cảnh báo khi khởi động nếu không tìm thấy bộ nhớ đệm hình ảnh của client ở đó).
- Tùy chọn: ffmpeg (chỉ cho `tools/eatrax_song.py`).

## Cài đặt

1. Trích xuất cơ sở dữ liệu cầu thủ từ client của bạn:
   `python extract_fifadb.py D:\FO3ID\32795` → `gamedata/fifadb.sqlite`.
2. Giá thị trường (tùy chọn): `python tools/fa_sync.py` → `gamedata/fa_prices.json` (lấy dữ liệu từ
   fifaaddict.com một cách lịch sự; không có nó thì giá tính theo công thức chỉ số).
3. Chứng chỉ TLS cho máy chủ API được client ghi cứng, `APSEODESK172` (chấp nhận tự ký):

   ```
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=APSEODESK172" -addext "subjectAltName=DNS:APSEODESK172" -keyout key.pem -out cert.pem
   python -c "open('certs/server.pem','w').write(open('cert.pem').read()+open('key.pem').read())"
   ```

4. File hosts (với quyền quản trị): `127.0.0.1 APSEODESK172`.
5. Build launcher một lần (`launcher/fifalauncher.cs`, lệnh build ghi bên trong), rồi nhấp đúp
   **`play.bat`**: nó mở cửa sổ máy chủ (`python start_all.py` = `http_config.py 443 --tls` +
   `messenger.py`; đóng cửa sổ đó để dừng máy chủ) và chạy game mà không hiện hộp thoại UAC.

6. Hoặc làm tay: `python start_all.py`, rồi chạy client với các tham số máy chủ (giống những gì
   `launcher/fifalauncher.exe` và `launch_game.ps1` truyền vào):

   ```
   fifazf.exe -QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp -QUICKMATCH/NOTISERVER=127.0.0.1:28001 -FIFA/LAUNCHER/PID=<pid> -PUBLISHER/GARENA/TOKEN=testtoken -LOCALE/PUBLISHING_REGION=ID -DUMPTRUCK/SERVER=127.0.0.1 region id token testtoken
   ```

## Các file

| File | Vai trò |
|---|---|
| `http_config.py` | Backend REST mà client gọi (`https://APSEODESK172`): đăng nhập, tài khoản, HLV, tạo CLB, đội hình, giải đấu, cúp, thị trường, nâng cấp, giao dịch, cửa hàng, vật phẩm, Bag, quà hằng ngày, bảng tĩnh, và `/cdn/` (phục vụ logo và thẻ từ `_cache` của chính client). Dữ liệu lưu ở `gamedata/state.json`. Biến môi trường: `FO3_LANGUAGE` (mặc định `ind`), `FO3_GAME` (thư mục client), `FO3_ASSETS`, `FO3_HALF_LENGTH`, `FO3_ADMIN_PORT`. |
| `messenger.py` | Máy chủ thông báo ở `:28002`. Khung `<u16 LE len><u16 type=2><Blowfish-CBC(key "kueec", IV 0) of JSON+"\n">`; trả lời `auth`, `ping`, `signon`. `python messenger.py --selftest`. |
| `admin.py` + `admin/index.html` | Trang quản trị (do `http_config.py` khởi động, chỉ truy cập từ máy này, không mật khẩu). Tab Cửa hàng lưu vào `gamedata/shop.json`. Mọi chữ trên trang, kể cả thông báo lỗi, nằm trong các bảng `I18N` ở cuối `admin.py`, mỗi ngôn ngữ một bảng; thêm ngôn ngữ mới chỉ cần thêm một bảng, và `python admin.py` kiểm tra mọi bảng có cùng khóa. |
| `responses/` | Body JSON cho từng endpoint (`/a/b/c` → `responses/a_b_c.json`, đọc lại ở mỗi yêu cầu). Cấu trúc lấy từ mã AS3 của client. |
| `extract_fifadb.py` | Cơ sở dữ liệu cầu thủ của client (`data_0.big`, RefPack + Blowfish) → SQLite. |
| `gen_teams.py` | Đội hình khởi đầu và tóm tắt CLB từ `gamedata/fifadb.sqlite`. |
| `tools/eatrax_song.py` | Đặt một bài hát lên đầu nhạc menu EA Trax dưới dạng EALayer3, thay TrackID 1 (sửa `data_0.big` / `data_1.big` bằng cách ghi nối thêm; `--restore` khôi phục bản gốc). Làm game crash sau trận, xem lỗi đã biết. |
| `tools/fa_sync.py` | Đồng bộ giá từ fifaaddict.com. |
| `tools/fo4_season.py` | Thêm thẻ 26 LIVE và 25 LIVE của FIFA Online 4 (dữ liệu fifaaddict, chỉ số tính là +0) thành hai mùa mới với biểu tượng mùa của FO4: `fetch`, `collect` + `import`, `build`, `install` (ghi đè các mục trong `data_0.big` tại chỗ vì kích thước tệp không được đổi, và ghi nối thêm vào `Label.big` và `Module.big`; `restore` khôi phục tất cả). `hud` chỉ vá `Module.big`, cho client đã cài mùa giải từ trước: ô tên cầu thủ trong trận trước đây hiện huy hiệu '17 cho mọi thẻ 2017 và FO4, giờ hiện mùa của chính thẻ đó. |
| `tools/fa_faces.py` | Thêm ảnh mặt nhỏ của cầu thủ còn thiếu trong bộ nhớ đệm của client (fifaaddict có cùng loại PNG 128x128); `--crests` thêm logo CLB còn thiếu (đa số CLB không có trong bộ nhớ đệm nên game hiện logo mặc định); `--staffs` thêm ảnh staff (bộ nhớ đệm chỉ có 7 trong 71 staff máy chủ phát). Chạy tiếp được nếu bị ngắt, `--remove` hoàn tác. |
| `tools/draft_icons.py` | Vẽ biểu tượng Shop cho các gói draft (bộ nhớ đệm của client không có ảnh draft) vào `assets/externalAssets/shop/`, máy chủ gửi các ảnh này trước ảnh của client; `<icon> <tag> <picks>` vẽ thêm một biểu tượng cho gói tạo trên trang admin. Cần Pillow. |
| `tools/re/` | Công cụ hỗ trợ dịch ngược: `bigdir.py` (bảng lưu trữ BIg4), `refpack.py` (codec RefPack), `eadb.py` (bảng cơ sở dữ liệu "DB" của EA), `abc*.py` (phân tích / tìm kiếm / khai thác cấu trúc bytecode AS3), `gfxx.py` (SWF giao diện), `memgrab.py`, `dbwin.py` (đầu ra debug của client), `relay_emu.py` (bộ mã hóa gói relay PvP và relay thử nghiệm), `gamectl.ps1` (điều khiển cửa sổ client khi kiểm thử). |
| `blaze.py`, `server.py`, `test_client.py`, `analyze_capture.py` | Khung EA Blaze (Fire/TDF) và máy chủ kiểm thử loopback từ giai đoạn đầu của dự án; sau đó hóa ra client dùng REST + messenger. |
| `analysis/` | Các script phân tích client ban đầu (chuỗi, section PE, endpoint mạng). |
| `FO3ID-private-server.md`, `reports/` | Phát hiện và báo cáo tiến độ (`reports/` viết bằng tiếng Indonesia). |

## Kiểm thử

```
python run_tests.py
```

Chạy tự kiểm thử Blaze/loopback và `test_league.py`, file chạy qua mọi tính năng backend (tạo CLB, giải
đấu, cúp, thị trường, nâng cấp, giao dịch, cửa hàng, quà hằng ngày, API quản trị, xóa HLV) trên một tài
khoản mới. Cần `gamedata/fifadb.sqlite`.

## Người đóng góp

- **SoloPlayer** — chủ dự án, kiểm thử trong client thật.
- **Claude** (trợ lý AI của Anthropic, qua Claude Code) — dịch ngược và phần lớn mã máy chủ, viết cùng
  chủ dự án.

## Giấy phép

[GNU GPL v3](LICENSE) cho mã và tài liệu trong kho này. FIFA Online 3, client, dữ liệu, tài nguyên và
nhạc của game thuộc về chủ sở hữu tương ứng và không nằm trong giấy phép này.
