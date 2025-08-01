document.addEventListener('DOMContentLoaded', () => {
  loadQuote();
  loadProducts();
  updateYear();
});

function loadQuote() {
  const quotes = [
    "La lumière que tu cherches à l’extérieur brille déjà en toi.",
    "Chaque matin est une nouvelle chance de s’illuminer.",
    "La paix intérieure commence là où les attentes cessent."
  ];
  const randomIndex = Math.floor(Math.random() * quotes.length);
  const quoteElement = document.getElementById('dailyQuote');
  quoteElement.textContent = quotes[randomIndex];
}

async function loadProducts() {
  try {
    const response = await fetch('assets/data/products.json');
    const products = await response.json();
    const productsGrid = document.getElementById('productGrid');
    productsGrid.innerHTML = '';
    products.forEach(product => {
      const productCard = document.createElement('div');
      productCard.className = 'product-card';
      productCard.innerHTML = `
        <img src="${product.image}" alt="${product.title}">
        <h3>${product.title}</h3>
        <p>${product.description}</p>
        <a href="${product.link}" class="support-button" target="_blank">Découvrir</a>
      `;
      productsGrid.appendChild(productCard);
    });
  } catch (error) {
    console.error('Erreur lors du chargement des produits:', error);
  }
}

function updateYear() {
  const yearSpan = document.getElementById('year');
  if (yearSpan) {
    yearSpan.textContent = new Date().getFullYear();
  }
}
