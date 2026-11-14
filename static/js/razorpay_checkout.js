/**
 * Razorpay Sandbox / Dummy Payment Checkout System.
 * Injects and manages the Razorpay Dummy Checkout Modal with authentic UI,
 * tabbed payment methods (Cards, UPI/QR, Netbanking, Wallets), test data auto-fill,
 * backend order creation, and cryptographic verification callback.
 */

(function () {
  'use strict';

  let rzpModalEl = null;
  let activeOptions = null;
  let activeTab = 'upi';
  let activeOrderId = null;

  function injectModalHTML() {
    if (document.getElementById('rzpModalBackdrop')) return;

    const modalHTML = `
      <div id="rzpModalBackdrop" class="rzp-backdrop">
        <div class="rzp-modal" role="dialog" aria-modal="true">
          <!-- Header -->
          <div class="rzp-header">
            <button class="rzp-close-btn" id="rzpCloseBtn" aria-label="Close Payment Modal">&times;</button>
            <div class="rzp-header-top">
              <div class="rzp-brand">
                <div class="rzp-logo-badge">P</div>
                <div class="rzp-brand-details">
                  <h3 id="rzpMerchantName">Smart Parking AI</h3>
                  <p id="rzpDescription">Smart Parking Checkout</p>
                </div>
              </div>
              <div class="rzp-test-badge">
                <i class="fas fa-flask"></i> TEST MODE
              </div>
            </div>
            <div class="rzp-amount-row">
              <span class="rzp-amount-label">Amount Payable</span>
              <span class="rzp-amount-val" id="rzpAmountDisplay">₹0.00</span>
            </div>
          </div>

          <!-- Method Tabs -->
          <div class="rzp-tabs">
            <button type="button" class="rzp-tab active" data-tab="upi">
              <i class="fas fa-qrcode"></i> UPI / QR
            </button>
            <button type="button" class="rzp-tab" data-tab="cards">
              <i class="fas fa-credit-card"></i> Card
            </button>
            <button type="button" class="rzp-tab" data-tab="netbanking">
              <i class="fas fa-university"></i> Netbanking
            </button>
            <button type="button" class="rzp-tab" data-tab="wallets">
              <i class="fas fa-wallet"></i> Wallets
            </button>
          </div>

          <!-- Body Panels -->
          <div class="rzp-body">
            <!-- UPI Panel -->
            <div class="rzp-panel active" id="rzpPanelUpi">
              <div class="rzp-qr-wrapper">
                <div class="rzp-qr-img">
                  <!-- SVG Mock QR Code -->
                  <svg width="120" height="120" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect width="100" height="100" fill="#ffffff"/>
                    <rect x="10" y="10" width="30" height="30" rx="4" stroke="#0f172a" stroke-width="6"/>
                    <rect x="20" y="20" width="10" height="10" fill="#ec4899"/>
                    <rect x="60" y="10" width="30" height="30" rx="4" stroke="#0f172a" stroke-width="6"/>
                    <rect x="70" y="20" width="10" height="10" fill="#ec4899"/>
                    <rect x="10" y="60" width="30" height="30" rx="4" stroke="#0f172a" stroke-width="6"/>
                    <rect x="20" y="70" width="10" height="10" fill="#ec4899"/>
                    <rect x="45" y="45" width="10" height="10" fill="#0f172a"/>
                    <rect x="60" y="60" width="12" height="12" fill="#0f172a"/>
                    <rect x="78" y="60" width="12" height="12" fill="#0f172a"/>
                    <rect x="60" y="78" width="12" height="12" fill="#0f172a"/>
                    <rect x="78" y="78" width="12" height="12" fill="#ec4899"/>
                  </svg>
                </div>
                <div style="font-size:12.5px; font-weight:700; color:#1e293b;">Scan QR to Pay with any UPI App</div>
                <div class="rzp-qr-apps">
                  <span class="rzp-qr-app-pill">GPay</span>
                  <span class="rzp-qr-app-pill">PhonePe</span>
                  <span class="rzp-qr-app-pill">Paytm</span>
                  <span class="rzp-qr-app-pill">BHIM</span>
                </div>
              </div>
              <div class="rzp-form-group">
                <label>Or enter UPI ID / VPA</label>
                <input type="text" class="rzp-input" id="rzpUpiInput" placeholder="driver@okhdfcbank" value="smartpark.driver@upi" />
              </div>
            </div>

            <!-- Cards Panel -->
            <div class="rzp-panel" id="rzpPanelCards">
              <button type="button" class="rzp-test-card-btn" id="rzpFillTestCardBtn">
                <i class="fas fa-magic"></i> Auto-fill Dummy Test Card (Visa)
              </button>
              <div class="rzp-form-group">
                <label>Card Number</label>
                <input type="text" class="rzp-input" id="rzpCardNumber" placeholder="4111 2222 3333 4444" maxlength="19" />
              </div>
              <div class="rzp-row">
                <div class="rzp-form-group" style="flex:1;">
                  <label>Expiry (MM/YY)</label>
                  <input type="text" class="rzp-input" id="rzpCardExpiry" placeholder="12/28" maxlength="5" />
                </div>
                <div class="rzp-form-group" style="flex:1;">
                  <label>CVV</label>
                  <input type="password" class="rzp-input" id="rzpCardCvv" placeholder="123" maxlength="4" />
                </div>
              </div>
              <div class="rzp-form-group">
                <label>Cardholder Name</label>
                <input type="text" class="rzp-input" id="rzpCardName" placeholder="Driver Name" value="Smart Parking Driver" />
              </div>
            </div>

            <!-- Netbanking Panel -->
            <div class="rzp-panel" id="rzpPanelNetbanking">
              <label style="font-size:12px; font-weight:600; color:#475569; margin-bottom:10px; display:block;">Select Bank</label>
              <div class="rzp-radio-grid">
                <div class="rzp-radio-option selected" data-value="HDFC Bank">
                  <i class="fas fa-building-columns" style="color:#ec4899;"></i> HDFC Bank
                </div>
                <div class="rzp-radio-option" data-value="State Bank of India">
                  <i class="fas fa-building-columns" style="color:#ec4899;"></i> SBI
                </div>
                <div class="rzp-radio-option" data-value="ICICI Bank">
                  <i class="fas fa-building-columns" style="color:#ea580c;"></i> ICICI Bank
                </div>
                <div class="rzp-radio-option" data-value="Axis Bank">
                  <i class="fas fa-building-columns" style="color:#9333ea;"></i> Axis Bank
                </div>
              </div>
            </div>

            <!-- Wallets Panel -->
            <div class="rzp-panel" id="rzpPanelWallets">
              <label style="font-size:12px; font-weight:600; color:#475569; margin-bottom:10px; display:block;">Select Wallet</label>
              <div class="rzp-radio-grid">
                <div class="rzp-radio-option selected" data-value="Paytm Wallet">
                  <i class="fas fa-wallet" style="color:#ec4899;"></i> Paytm
                </div>
                <div class="rzp-radio-option" data-value="PhonePe Wallet">
                  <i class="fas fa-wallet" style="color:#6366f1;"></i> PhonePe
                </div>
                <div class="rzp-radio-option" data-value="Amazon Pay">
                  <i class="fas fa-wallet" style="color:#f59e0b;"></i> Amazon Pay
                </div>
                <div class="rzp-radio-option" data-value="MobiKwik">
                  <i class="fas fa-wallet" style="color:#ef4444;"></i> MobiKwik
                </div>
              </div>
            </div>
          </div>

          <!-- Footer & Action CTA -->
          <div class="rzp-footer">
            <button type="button" class="rzp-pay-btn" id="rzpPayBtn">
              <i class="fas fa-lock"></i> <span id="rzpPayBtnLabel">Pay ₹0.00</span>
            </button>
            <div class="rzp-security-note">
              <i class="fas fa-shield-alt" style="color:#ec4899;"></i> Secured by 256-bit SSL Encryption &bull; Razorpay Sandbox
            </div>
            <div class="rzp-fail-toggle">
              Testing error handling? <a id="rzpSimulateFailLink">Simulate Payment Failure ✗</a>
            </div>
          </div>

          <!-- Overlay for Processing / Result -->
          <div class="rzp-status-overlay" id="rzpStatusOverlay">
            <div class="rzp-spinner" id="rzpOverlaySpinner"></div>
            <div class="rzp-success-icon" id="rzpOverlaySuccess" style="display:none;">
              <i class="fas fa-check"></i>
            </div>
            <div class="rzp-error-icon" id="rzpOverlayError" style="display:none;">
              <i class="fas fa-times"></i>
            </div>
            <h4 id="rzpOverlayTitle" style="margin:0; font-size:17px; color:#0f172a;">Processing Payment...</h4>
            <p id="rzpOverlayMsg" style="margin:0; font-size:13px; color:#64748b;">Please do not refresh or close this window.</p>
          </div>
        </div>
      </div>
    `;

    const container = document.createElement('div');
    container.innerHTML = modalHTML;
    document.body.appendChild(container.firstElementChild);
    rzpModalEl = document.getElementById('rzpModalBackdrop');

    setupEventListeners();
  }

  function setupEventListeners() {
    if (!rzpModalEl) return;

    // Close button & backdrop click
    document.getElementById('rzpCloseBtn').addEventListener('click', closeModal);
    rzpModalEl.addEventListener('click', function (e) {
      if (e.target === rzpModalEl) closeModal();
    });

    // Tab switcher
    const tabBtns = rzpModalEl.querySelectorAll('.rzp-tab');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', function () {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeTab = btn.getAttribute('data-tab');

        const panels = rzpModalEl.querySelectorAll('.rzp-panel');
        panels.forEach(p => p.classList.remove('active'));

        const targetPanel = document.getElementById('rzpPanel' + capitalize(activeTab));
        if (targetPanel) targetPanel.classList.add('active');
      });
    });

    // Netbanking & Wallets radio selections
    rzpModalEl.querySelectorAll('.rzp-radio-grid').forEach(grid => {
      const options = grid.querySelectorAll('.rzp-radio-option');
      options.forEach(opt => {
        opt.addEventListener('click', () => {
          options.forEach(o => o.classList.remove('selected'));
          opt.classList.add('selected');
        });
      });
    });

    // Auto-fill test card button
    const fillBtn = document.getElementById('rzpFillTestCardBtn');
    if (fillBtn) {
      fillBtn.addEventListener('click', () => {
        document.getElementById('rzpCardNumber').value = '4111 2222 3333 4444';
        document.getElementById('rzpCardExpiry').value = '12/28';
        document.getElementById('rzpCardCvv').value = '888';
        document.getElementById('rzpCardName').value = 'Driver Test User';
      });
    }

    // Payment action button
    document.getElementById('rzpPayBtn').addEventListener('click', () => {
      executePayment(true);
    });

    // Simulate failure link
    document.getElementById('rzpSimulateFailLink').addEventListener('click', (e) => {
      e.preventDefault();
      executePayment(false);
    });
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function closeModal() {
    if (rzpModalEl) {
      rzpModalEl.classList.remove('rzp-active');
    }
    const overlay = document.getElementById('rzpStatusOverlay');
    if (overlay) overlay.classList.remove('active');

    if (activeOptions && typeof activeOptions.onDismiss === 'function') {
      activeOptions.onDismiss();
    }
    activeOptions = null;
  }

  async function executePayment(simulateSuccess = true) {
    if (!activeOptions) return;

    const overlay = document.getElementById('rzpStatusOverlay');
    const spinner = document.getElementById('rzpOverlaySpinner');
    const succIcon = document.getElementById('rzpOverlaySuccess');
    const errIcon = document.getElementById('rzpOverlayError');
    const title = document.getElementById('rzpOverlayTitle');
    const msg = document.getElementById('rzpOverlayMsg');

    overlay.classList.add('active');
    spinner.style.display = 'block';
    succIcon.style.display = 'none';
    errIcon.style.display = 'none';
    title.textContent = 'Authorizing with Razorpay Sandbox...';
    msg.textContent = 'Connecting to banking network...';

    // Simulated short network delay for authentic user experience
    await new Promise(r => setTimeout(r, 900));

    if (!simulateSuccess) {
      spinner.style.display = 'none';
      errIcon.style.display = 'flex';
      title.textContent = 'Payment Failed';
      title.style.color = '#dc2626';
      msg.textContent = 'Declined by test issuer bank. Please try another payment method.';

      setTimeout(() => {
        overlay.classList.remove('active');
        if (typeof activeOptions.onFailure === 'function') {
          activeOptions.onFailure({
            code: 'PAYMENT_FAILED',
            description: 'Declined by dummy payment issuer.'
          });
        }
      }, 1400);
      return;
    }

    // Determine chosen payment method
    let methodLabel = 'UPI / QR';
    if (activeTab === 'cards') {
      methodLabel = 'Card (Visa Test)';
    } else if (activeTab === 'netbanking') {
      const selected = rzpModalEl.querySelector('#rzpPanelNetbanking .rzp-radio-option.selected');
      methodLabel = 'Netbanking - ' + (selected ? selected.getAttribute('data-value') : 'HDFC Bank');
    } else if (activeTab === 'wallets') {
      const selected = rzpModalEl.querySelector('#rzpPanelWallets .rzp-radio-option.selected');
      methodLabel = 'Wallet - ' + (selected ? selected.getAttribute('data-value') : 'Paytm');
    }

    const mockPaymentId = 'pay_' + Math.random().toString(36).substring(2, 16);
    const mockSignature = 'mock_sig_' + (activeOrderId || 'order_direct') + '_' + mockPaymentId;

    // Verify on backend
    try {
      title.textContent = 'Verifying Transaction...';
      msg.textContent = 'Confirming signature and logging in database...';

      const verifyPayload = {
        razorpay_payment_id: mockPaymentId,
        razorpay_order_id: activeOrderId || ('order_' + Math.random().toString(36).substring(2, 16)),
        razorpay_signature: mockSignature,
        amount: activeOptions.amount,
        booking_id: activeOptions.bookingId || null,
        overstay_id: activeOptions.overstayId || null,
        method: methodLabel,
        type: activeOptions.type || 'booking'
      };

      const res = await fetch('/api/payment/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(verifyPayload)
      });

      const data = await res.json();

      if (res.ok && data.status === 'success') {
        spinner.style.display = 'none';
        succIcon.style.display = 'flex';
        title.textContent = 'Payment Successful! 🎉';
        title.style.color = '#15803d';
        msg.textContent = `Receipt issued for ₹${Number(activeOptions.amount).toFixed(2)}. Updating reservation...`;

        setTimeout(() => {
          const successCallback = activeOptions ? activeOptions.onSuccess : null;
          closeModal();
          if (typeof successCallback === 'function') {
            successCallback({
              razorpay_payment_id: mockPaymentId,
              razorpay_order_id: verifyPayload.razorpay_order_id,
              razorpay_signature: mockSignature,
              amount: activeOptions ? activeOptions.amount : verifyPayload.amount,
              method: methodLabel,
              transaction: data.transaction
            });
          }
        }, 1100);
      } else {
        throw new Error(data.message || 'Payment signature verification failed.');
      }
    } catch (err) {
      spinner.style.display = 'none';
      errIcon.style.display = 'flex';
      title.textContent = 'Verification Error';
      title.style.color = '#dc2626';
      msg.textContent = err.message || 'Failed to verify transaction.';

      setTimeout(() => {
        overlay.classList.remove('active');
        if (activeOptions && typeof activeOptions.onFailure === 'function') {
          activeOptions.onFailure(err);
        }
      }, 1500);
    }
  }

  /**
   * Main Public Entrypoint: opens Razorpay checkout modal
   * @param {Object} options
   */
  window.openRazorpayModal = async function (options) {
    injectModalHTML();

    activeOptions = Object.assign({
      amount: 80.0,
      title: 'Smart Parking AI',
      description: 'Parking Slot Reservation Checkout',
      bookingId: null,
      overstayId: null,
      type: 'booking',
      onSuccess: null,
      onFailure: null,
      onDismiss: null
    }, options);

    const amtFloat = parseFloat(activeOptions.amount) || 0.0;
    const formattedAmt = '₹' + amtFloat.toFixed(2);

    document.getElementById('rzpMerchantName').textContent = activeOptions.title;
    document.getElementById('rzpDescription').textContent = activeOptions.description;
    document.getElementById('rzpAmountDisplay').textContent = formattedAmt;
    document.getElementById('rzpPayBtnLabel').textContent = `Pay ${formattedAmt}`;

    // Request authentic order from backend
    try {
      const orderRes = await fetch('/api/payment/create-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          amount: amtFloat,
          booking_id: activeOptions.bookingId,
          notes: {
            description: activeOptions.description,
            type: activeOptions.type
          }
        })
      });
      const orderData = await orderRes.json();
      if (orderRes.ok && orderData.status === 'success' && orderData.order) {
        activeOrderId = orderData.order.id;
      } else {
        activeOrderId = 'order_mock_' + Math.random().toString(36).substring(2, 14);
      }
    } catch (e) {
      activeOrderId = 'order_mock_' + Math.random().toString(36).substring(2, 14);
    }

    rzpModalEl.classList.add('rzp-active');
  };

  // Standalone alias
  window.RazorpayCheckout = {
    open: window.openRazorpayModal
  };

})();
