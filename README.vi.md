# FO3ID Private Server

[English](README.md) | [Bahasa Indonesia](README.id.md) | [简体中文](README.zh-CN.md) | [ไทย](README.th.md) | **Tiếng Việt** | [한국어](README.ko.md)

> Bản dịch của [README.md](README.md). Nếu có chỗ khác nhau, README.md là bản mới nhất.

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
- Trang quản trị web tại http://127.0.0.1:8088/ (EP, cầu thủ, gói, quà, quà hằng ngày, thưởng sau trận, Cửa hàng, nhật ký)
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
  Legend, …).
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

Chưa làm: chế độ online (xếp hạng, giao hữu, King of the Hill), Road to World, mô phỏng giải đấu.

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
| `tools/fa_faces.py` | Thêm ảnh mặt nhỏ của cầu thủ còn thiếu trong bộ nhớ đệm của client (fifaaddict có cùng loại PNG 128x128); `--crests` thêm logo CLB còn thiếu (đa số CLB không có trong bộ nhớ đệm nên game hiện logo mặc định). Chạy tiếp được nếu bị ngắt, `--remove` hoàn tác. |
| `tools/re/` | Công cụ hỗ trợ dịch ngược: `bigdir.py` (bảng lưu trữ BIg4), `refpack.py` (codec RefPack), `eadb.py` (bảng cơ sở dữ liệu "DB" của EA), `abc*.py` (phân tích / tìm kiếm / khai thác cấu trúc bytecode AS3), `gfxx.py` (SWF giao diện), `memgrab.py`, `gamectl.ps1` (điều khiển cửa sổ client khi kiểm thử). |
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
