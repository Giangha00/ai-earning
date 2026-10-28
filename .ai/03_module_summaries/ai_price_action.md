# Module Summary: Price Action Analyzer (`ai_price_action.py`)

## 1. Mục đích
Hiện thực hóa CHƯƠNG 1 (Tất cả 6 kịch bản thị trường Case-by-Case) và CHƯƠNG 3.2 (Thuật toán nhận diện vùng nén - Compression Detection) theo Sổ tay thuật toán Bot AI Trading Forex Chuyên Sâu.

## 2. 6 Kịch bản thị trường (6 Market Cases)
1. **Case A: Trend Tăng / Giảm Rõ Ràng (Smooth Trend)**:
   - Cấu trúc High > High, Low > Low (Tăng) hoặc High < High, Low < Low (Giảm).
   - Đánh giá: Thị trường lành (Winrate > 65%). Cho phép vào lệnh BUY/SELL khi giá hồi về Căn cứ Bò/Gấu gần nhất (EMA20 / Swing level) + nến xác nhận.
2. **Case B: Đi Ngang Có Quy Luật (Structured Sideway / Compression)**:
   - Thuật toán nhận diện vùng nén qua 3 điều kiện:
     - ĐK1: $\text{ATR}(5) < 0.65 \times \text{ATR}(20)$ (Biên độ giảm > 35%).
     - ĐK2: Swing Amplitude thu hẹp dần ($D_1 > D_2 > D_3$).
     - ĐK3: Hình học vùng nén (Tam giác Tăng, Tam giác Giảm, Tam giác Cân, Hộp Rectangle).
   - Hành động: Cho phép vào lệnh khi nến Breakout thân dài đóng cửa dứt khoát ngoài vùng nén. Tỷ lệ R:R cao (1:2 đến 1:3.5).
3. **Case C: Đi Ngang Hỗn Loạn / Hình Cái Loa (Broadening Chaos Market)**:
   - Đỉnh sau cao hơn đỉnh trước VÀ Đáy sau thấp hơn đáy trước, nến râu dài quét 2 đầu.
   - Hành động: CẤM TUYỆT ĐỐI VÀO LỆNH (STRICT NO TRADE). AI tự động gắn nhãn BROADENING_CHAOS và khóa phát tín hiệu.
4. **Case D: Bẫy Phá Giả & Sweep Thanh Khoản (Liquidity Trap)**:
   - Giá đâm thủng cản Đỉnh/Đáy cũ để kích Stop Loss của số đông, sau đó rút chân dội ngược lại bằng nến Engulfing.
   - Hành động: Cho phép vào lệnh ĐẢO CHIỀU ngay sau cây nến Engulfing đóng cửa quay lại bên trong vùng cản.
5. **Case E: Sóng Dẫn Hướng & Đảo Chiều Đột Ngột (Directional Leading Wave)**:
   - Sóng dốc đứng, thân nến dài dứt khoát đi ngược xu hướng trước đó, phá căn cứ chính.
   - Hành động: CHỜ XÁC NHẬN (RETEST). Không vào lệnh ở đỉnh sóng, chờ giá nén nhẹ lại rồi mới vào thuận chiều sóng dẫn hướng.
6. **Case F: Bão Tin Tức & Giãn Spread Rollover (Technical Artifacts)**:
   - Khung giờ giao ngày Rollover (4h-5h sáng VN) hoặc Spread giãn đột biến $\ge 25$ points.
   - Hành động: CẦU DAO TỰ ĐỘNG ngắt Bot AI để tránh trượt giá và giãn spread.
